import io
import unittest
from unittest.mock import patch

from azure.core.exceptions import ResourceNotFoundError
from botocore.exceptions import ClientError

from app import create_app
from app.extensions import db
from app.models.migration import Migration, MigrationFile
from app.models.user import User
from app.services import s3_migration_service as service


class _Properties:
    def __init__(self, size, etag="destination-etag"):
        self.size = size
        self.etag = etag


class _Blob:
    def __init__(self, fail_once=False):
        self.size = None
        self.upload_calls = 0
        self.fail_once = fail_once
        self.last_stream = None

    def get_blob_properties(self):
        if self.size is None:
            raise ResourceNotFoundError(message="not found")
        return _Properties(self.size)

    def upload_blob(self, stream, overwrite=False):
        self.upload_calls += 1
        self.last_stream = stream
        self.assert_no_overwrite(overwrite)
        if self.fail_once and self.upload_calls == 1:
            raise ClientError({"Error": {"Code": "SlowDown", "Message": "retry"}}, "PutObject")
        self.size = len(stream.read())

    @staticmethod
    def assert_no_overwrite(overwrite):
        if overwrite:
            raise AssertionError("migration must not overwrite destination objects")


class _Container:
    def __init__(self, blob):
        self.blob = blob

    def get_blob_client(self, _key):
        return self.blob


class _S3Client:
    def __init__(self, payload=b"payload"):
        self.payload = payload
        self.calls = 0

    def get_object(self, **_kwargs):
        self.calls += 1
        return {"Body": io.BytesIO(self.payload), "ContentLength": len(self.payload), "ETag": '"source-etag"'}


class _PermanentFailureS3Client(_S3Client):
    def get_object(self, **_kwargs):
        self.calls += 1
        raise ClientError({"Error": {"Code": "AccessDenied", "Message": "not returned"}}, "GetObject")


class _GuardedStream:
    """Fails if application code tries to read the whole object at once."""
    def __init__(self, payload):
        self.payload = payload
        self.offset = 0
        self.closed = False

    def read(self, size=-1):
        if size is None or size < 0:
            raise AssertionError("full-object buffering is not allowed")
        chunk = self.payload[self.offset:self.offset + size]
        self.offset += len(chunk)
        return chunk

    def close(self):
        self.closed = True


class _StreamingBlob(_Blob):
    def upload_blob(self, stream, overwrite=False):
        self.upload_calls += 1
        self.last_stream = stream
        self.assert_no_overwrite(overwrite)
        total = 0
        while True:
            chunk = stream.read(2)
            if not chunk:
                break
            total += len(chunk)
        self.size = total


class _WrongSizeBlob(_Blob):
    def upload_blob(self, stream, overwrite=False):
        self.upload_calls += 1
        self.assert_no_overwrite(overwrite)
        stream.read()
        self.size = 1


class _AwsSession:
    def __init__(self, client):
        self.client_value = client

    def client(self, name):
        assert name == "s3"
        return self.client_value


class S3MigrationServiceTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-only-secret-key-not-used-in-production",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "WTF_CSRF_ENABLED": False,
        })
        with self.app.app_context():
            db.create_all()
            user = User(name="Test User", email="migration@example.com", password_hash="hash")
            db.session.add(user)
            db.session.commit()
            self.migration = Migration(
                migration_id="s3-phase2-test", user_id=user.id, source_cloud="aws", target_cloud="azure",
                resource_type="s3", resource_name="source-bucket", status="interrupted", total_files=1,
                destination_resource_group="rg", destination_storage_account="account", destination_container="data",
            )
            db.session.add(self.migration)
            db.session.commit()
            db.session.add(MigrationFile(migration_id=self.migration.id, object_key="large.bin", size_bytes=7, batch_number=1))
            db.session.commit()
            # Flask-SQLAlchemy removes the scoped session when this setup app
            # context exits. Keep scalar identifiers only; tests that need ORM
            # state re-query it in their own active app context.
            self.migration_id = self.migration.migration_id
            self.user_id = user.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_streamed_object_is_verified_and_persisted(self):
        blob, s3 = _Blob(), _S3Client(b"payload")
        with self.app.app_context(), patch.object(service, "_container_client", return_value=_Container(blob)):
            result = service.execute_s3_migration("s3-phase2-test", _AwsSession(s3), {})
            record = MigrationFile.query.filter_by(object_key="large.bin").one()
            self.assertTrue(result["success"])
            self.assertEqual(record.status, "verified")
            self.assertEqual(record.verification_status, "size_verified")
            self.assertIs(blob.last_stream.__class__, io.BytesIO)
            self.assertEqual(s3.calls, 1)

    def test_transient_failure_is_retried_without_overwrite(self):
        blob, s3 = _Blob(fail_once=True), _S3Client(b"payload")
        with self.app.app_context(), patch.object(service, "_container_client", return_value=_Container(blob)), patch.object(service.time, "sleep"):
            service.execute_s3_migration("s3-phase2-test", _AwsSession(s3), {})
            record = MigrationFile.query.filter_by(object_key="large.bin").one()
            self.assertEqual(record.status, "verified")
            self.assertEqual(blob.upload_calls, 2)

    def test_verified_object_is_not_transferred_again_on_resume(self):
        with self.app.app_context():
            record = MigrationFile.query.filter_by(object_key="large.bin").one()
            record.status = "verified"
            db.session.commit()
            s3 = _S3Client()
            with patch.object(service, "_container_client", return_value=_Container(_Blob())):
                result = service.execute_s3_migration("s3-phase2-test", _AwsSession(s3), {})
            self.assertTrue(result["success"])
            self.assertEqual(s3.calls, 0)

    def test_logical_batches_do_not_buffer_object_contents(self):
        batches = service.create_batches([
            {"key": "a", "size": service.BATCH_SIZE_LIMIT},
            {"key": "b", "size": 1},
        ])
        self.assertEqual(len(batches), 2)
        self.assertEqual(batches[0]["files"][0]["key"], "a")

    def test_large_stream_is_passed_to_azure_without_full_buffering(self):
        class GuardedS3(_S3Client):
            def get_object(self, **_kwargs):
                self.calls += 1
                return {"Body": _GuardedStream(b"large-payload"), "ContentLength": 13, "ETag": '"source-etag"'}

        blob, s3 = _StreamingBlob(), GuardedS3()
        with self.app.app_context(), patch.object(service, "_container_client", return_value=_Container(blob)):
            record = MigrationFile.query.filter_by(object_key="large.bin").one()
            record.size_bytes = 13
            migration = Migration.query.filter_by(migration_id=self.migration_id).one()
            migration.total_size_bytes = 13
            db.session.commit()
            result = service.execute_s3_migration("s3-phase2-test", _AwsSession(s3), {})
            self.assertTrue(result["success"])
            self.assertIsInstance(blob.last_stream, _GuardedStream)

    def test_permanent_provider_failure_is_not_retried_indefinitely(self):
        blob, s3 = _Blob(), _PermanentFailureS3Client()
        with self.app.app_context(), patch.object(service, "_container_client", return_value=_Container(blob)):
            result = service.execute_s3_migration("s3-phase2-test", _AwsSession(s3), {})
            record = MigrationFile.query.filter_by(object_key="large.bin").one()
            self.assertFalse(result["success"])
            self.assertEqual(record.status, "failed")
            self.assertEqual(record.attempt_count, 1)
            self.assertEqual(s3.calls, 1)

    def test_verification_failure_is_not_reported_as_success(self):
        blob, s3 = _WrongSizeBlob(), _S3Client(b"payload")
        with self.app.app_context(), patch.object(service, "_container_client", return_value=_Container(blob)):
            result = service.execute_s3_migration("s3-phase2-test", _AwsSession(s3), {})
            record = MigrationFile.query.filter_by(object_key="large.bin").one()
            self.assertFalse(result["success"])
            self.assertEqual(record.status, "failed")
            self.assertEqual(record.verification_status, "size_mismatch")
            self.assertEqual(record.bytes_transferred, 0)

    def test_retry_counts_and_transferred_bytes_are_persisted(self):
        blob, s3 = _Blob(fail_once=True), _S3Client(b"payload")
        with self.app.app_context(), patch.object(service, "_container_client", return_value=_Container(blob)), patch.object(service.time, "sleep"):
            result = service.execute_s3_migration("s3-phase2-test", _AwsSession(s3), {})
            record = MigrationFile.query.filter_by(object_key="large.bin").one()
            stored = Migration.query.filter_by(migration_id="s3-phase2-test").one()
            self.assertEqual(record.attempt_count, 2)
            self.assertEqual(result["retry_attempts"], 2)
            self.assertEqual(stored.transferred_bytes, 7)
            self.assertEqual(result["transferred_bytes"], 7)

    def test_terminal_migration_rejects_invalid_execution_transition(self):
        with self.app.app_context():
            migration = Migration.query.filter_by(migration_id=self.migration_id).one()
            migration.status = "completed"
            db.session.commit()
            s3 = _S3Client()
            result = service.execute_s3_migration("s3-phase2-test", _AwsSession(s3), {})
            self.assertFalse(result["success"])
            self.assertEqual(s3.calls, 0)

    def test_repeated_start_reuses_persisted_active_migration(self):
        with self.app.app_context():
            migration = Migration.query.filter_by(migration_id=self.migration_id).one()
            migration.status = "preparing"
            migration.uploaded_files = 1
            migration.transferred_bytes = 7
            db.session.commit()
            with patch.object(service._executor, "submit") as submit:
                result = service.start_s3_migration(_AwsSession(_S3Client()), {}, "source-bucket", user_id=self.user_id)
            self.assertTrue(result["success"])
            self.assertEqual(result["migration_id"], "s3-phase2-test")
            self.assertIn("already active", result["message"])
            submit.assert_not_called()
            self.assertEqual(Migration.query.filter_by(resource_name="source-bucket").count(), 1)
            persisted = Migration.query.filter_by(migration_id=self.migration_id).one()
            self.assertEqual(persisted.status, "preparing")
            self.assertEqual(persisted.uploaded_files, 1)
            self.assertEqual(persisted.transferred_bytes, 7)

    def test_progress_is_derived_from_persisted_object_state(self):
        with self.app.app_context():
            record = MigrationFile.query.filter_by(object_key="large.bin").one()
            record.status = "verified"
            record.bytes_transferred = 7
            migration = Migration.query.filter_by(migration_id=self.migration_id).one()
            service._refresh_counts(migration)
            db.session.commit()
            db.session.remove()
            persisted = Migration.query.filter_by(migration_id="s3-phase2-test").one()
            progress = service.migration_progress(persisted)
            self.assertEqual(progress["verified_files"], 1)
            self.assertEqual(progress["completed_batches"], 1)
            self.assertEqual(progress["transferred_bytes"], 7)


if __name__ == "__main__":
    unittest.main()
