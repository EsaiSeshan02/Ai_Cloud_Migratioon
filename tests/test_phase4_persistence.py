import json
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.extensions import db
from app.models.migration import Migration, MigrationFile
from app.models.report import Report
from app.models.user import User
from app.security.encryption import CredentialCipher
from app.services import s3_migration_service as s3_service
from app.services.report_service import generate_report, serialize_report


class Phase4PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-only-secret-key-not-used-in-production",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "WTF_CSRF_ENABLED": False,
        })
        with self.app.app_context():
            db.create_all()
            user = User(name="Persistence User", email="persistence@example.com", password_hash="hash")
            db.session.add(user)
            db.session.commit()
            self.user_id = user.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def test_active_identity_database_constraint_prevents_duplicate_active_rows(self):
        with self.app.app_context():
            first = Migration(migration_id="one", user_id=self.user_id, source_cloud="aws", target_cloud="azure",
                              resource_type="s3", resource_name="demo-bucket", status="preparing", active_identity="same")
            db.session.add(first)
            db.session.commit()
            db.session.add(Migration(migration_id="two", user_id=self.user_id, source_cloud="aws", target_cloud="azure",
                                     resource_type="s3", resource_name="demo-bucket", status="preparing", active_identity="same"))
            with self.assertRaises(IntegrityError):
                db.session.commit()
            db.session.rollback()

    def test_prepare_reuses_persisted_identity_without_provider_setup(self):
        with self.app.app_context(), patch.object(s3_service, "get_s3_objects", return_value={"success": True, "objects": []}):
            first = s3_service._prepare_migration(object(), {"subscription_id": "sub"}, "demo-bucket", {}, self.user_id)
            self.assertEqual(first["status"], "completed")
            # A completed migration has intentionally released its active
            # identity, so create a persisted interrupted record to exercise
            # safe start blocking/recovery instead.
            record = Migration(migration_id="resume-me", user_id=self.user_id, source_cloud="aws", target_cloud="azure",
                               resource_type="s3", resource_name="resume-bucket", status="interrupted", active_identity="resume-key")
            db.session.add(record)
            db.session.commit()
            with patch.object(s3_service, "_active_identity", return_value="resume-key"), \
                 patch.object(s3_service, "get_s3_objects") as list_objects:
                result = s3_service._prepare_migration(object(), {"subscription_id": "sub"}, "resume-bucket", {}, self.user_id)
            self.assertTrue(result["success"])
            self.assertIn("must be resumed", result["message"])
            list_objects.assert_not_called()

    def test_report_is_persisted_and_excludes_execution_configuration(self):
        with self.app.app_context():
            migration = Migration(migration_id="report-one", user_id=self.user_id, source_cloud="aws", target_cloud="azure",
                                  resource_type="s3", resource_name="safe-bucket", status="completed",
                                  execution_configuration=json.dumps({"client_secret": "do-not-store"}))
            db.session.add(migration)
            db.session.flush()
            db.session.add(MigrationFile(migration_id=migration.id, object_key="private-key-name", size_bytes=5,
                                         status="verified", verification_status="size_verified", bytes_transferred=5))
            db.session.commit()
            report = generate_report(migration)
            serialized = serialize_report(report)
            self.assertEqual(Report.query.count(), 1)
            self.assertEqual(serialized["report"]["bytes_transferred"], 5)
            self.assertNotIn("client_secret", json.dumps(serialized))
            self.assertNotIn("private-key-name", json.dumps(serialized))

    def test_authenticated_encryption_requires_environment_key_and_round_trips(self):
        cipher = CredentialCipher(Fernet.generate_key())
        encrypted = cipher.encrypt("transient-value")
        self.assertNotEqual(encrypted, "transient-value")
        self.assertEqual(cipher.decrypt(encrypted), "transient-value")
        with self.assertRaises(ValueError):
            CredentialCipher(None)

