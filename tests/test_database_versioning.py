"""Focused persistence and forward-only schema-versioning tests."""

import os
import tempfile
import unittest
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.database.migration_schema import upgrade_legacy_schema
from app.extensions import db
from app.models.migration import Migration, MigrationFile, MigrationPlan
from app.models.report import Report
from app.models.user import User
from app.security.audit_logger import AuditEvent
from app.utils.time import UTCDateTime, utc_now


ROOT = Path(__file__).resolve().parents[1]


class DatabaseVersioningTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-only-database-versioning-secret",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
        })
        with self.app.app_context():
            db.create_all()
            user = User(name="Database Owner", email="database-owner@example.com", password_hash="hash")
            db.session.add(user)
            db.session.commit()
            self.user_id = user.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def _migration(self, identifier="database-migration"):
        return Migration(
            migration_id=identifier,
            user_id=self.user_id,
            source_cloud="aws",
            target_cloud="azure",
            resource_type="s3",
            resource_name="database-bucket",
        )

    def test_schema_metadata_and_baseline_revision_exist(self):
        with self.app.app_context():
            tables = set(inspect(db.engine).get_table_names())
            self.assertTrue({
                "users", "migrations", "migration_files", "migration_plans",
                "migration_plan_resources", "reports", "audit_events",
            }.issubset(tables))
            self.assertIn("migrate", self.app.extensions)
        self.assertTrue((ROOT / "alembic.ini").is_file())
        self.assertTrue((ROOT / "Migrations" / "env.py").is_file())
        self.assertTrue((ROOT / "Migrations" / "versions" / "20260927_01_baseline_current_schema.py").is_file())
        self.assertTrue((ROOT / "Migrations" / "versions" / "20260927_02_execution_lifecycle.py").is_file())
        self.assertTrue((ROOT / "Migrations" / "versions" / "20260927_03_lambda_uncertain_blocker.py").is_file())
        script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
        self.assertEqual(script.get_current_head(), "20260927_03")

    def test_flask_migrate_uses_repository_alembic_configuration(self):
        with self.app.app_context():
            config = self.app.extensions["migrate"].migrate.get_config()
            self.assertEqual(
                Path(config.config_file_name).resolve(),
                (ROOT / "alembic.ini").resolve(),
            )
            self.assertEqual(
                Path(config.get_main_option("script_location")).resolve(),
                (ROOT / "Migrations").resolve(),
            )

    def test_legacy_database_upgrade_preserves_existing_rows(self):
        handle, path = tempfile.mkstemp(suffix=".sqlite")
        os.close(handle)
        engine = create_engine(f"sqlite:///{path}")
        try:
            with engine.begin() as connection:
                connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL, email VARCHAR(120) NOT NULL UNIQUE, password_hash VARCHAR(255) NOT NULL)"))
                connection.execute(text("CREATE TABLE migrations (id INTEGER PRIMARY KEY, migration_id VARCHAR(64) NOT NULL UNIQUE, user_id INTEGER, source_cloud VARCHAR(20) NOT NULL, target_cloud VARCHAR(20) NOT NULL, resource_type VARCHAR(50) NOT NULL, resource_name VARCHAR(255) NOT NULL, status VARCHAR(30) NOT NULL, total_files INTEGER NOT NULL DEFAULT 0, uploaded_files INTEGER NOT NULL DEFAULT 0, failed_files INTEGER NOT NULL DEFAULT 0, total_size_bytes BIGINT NOT NULL DEFAULT 0, total_batches INTEGER NOT NULL DEFAULT 0, started_at DATETIME, completed_at DATETIME, created_at DATETIME NOT NULL)"))
                connection.execute(text("CREATE TABLE migration_files (id INTEGER PRIMARY KEY, migration_id INTEGER NOT NULL, object_key VARCHAR(1024) NOT NULL, size_bytes BIGINT NOT NULL DEFAULT 0, batch_number INTEGER NOT NULL DEFAULT 1, status VARCHAR(30) NOT NULL, error_message TEXT, started_at DATETIME, completed_at DATETIME, created_at DATETIME NOT NULL)"))
                connection.execute(text("INSERT INTO users (id, name, email, password_hash) VALUES (1, 'Legacy', 'legacy@example.com', 'hash')"))
                connection.execute(text("INSERT INTO migrations (id, migration_id, user_id, source_cloud, target_cloud, resource_type, resource_name, status, created_at) VALUES (1, 'legacy-migration', 1, 'aws', 'azure', 's3', 'legacy-bucket', 'pending', CURRENT_TIMESTAMP)"))
                connection.execute(text("INSERT INTO migration_files (id, migration_id, object_key, status, created_at) VALUES (1, 1, 'legacy-key', 'pending', CURRENT_TIMESTAMP)"))
            with engine.begin() as connection:
                upgrade_legacy_schema(connection)
            inspector = inspect(engine)
            migration_columns = {column["name"] for column in inspector.get_columns("migrations")}
            file_columns = {column["name"] for column in inspector.get_columns("migration_files")}
            self.assertTrue({
                "plan_id", "active_identity", "execution_configuration", "failure_reason", "transferred_bytes",
                "cancellation_requested", "worker_token", "lease_expires_at", "last_heartbeat_at", "retry_count", "updated_at",
                "uncertain_external_operation",
            }.issubset(migration_columns))
            self.assertTrue({"source_etag", "destination_etag", "verification_status", "attempt_count", "bytes_transferred"}.issubset(file_columns))
            with engine.connect() as connection:
                self.assertEqual(connection.execute(text("SELECT migration_id FROM migrations WHERE id = 1")).scalar_one(), "legacy-migration")
                self.assertEqual(connection.execute(text("SELECT object_key FROM migration_files WHERE id = 1")).scalar_one(), "legacy-key")
        finally:
            engine.dispose()
            os.unlink(path)

    def test_required_uniqueness_and_owner_relationships_remain_enforced(self):
        with self.app.app_context():
            migration = self._migration()
            db.session.add(migration)
            db.session.flush()
            db.session.add(MigrationFile(migration_id=migration.id, object_key="one"))
            db.session.add(Report(report_id="database-report", user_id=self.user_id, migration_id=migration.id, status="pending"))
            db.session.commit()
            self.assertEqual(migration.user.id, self.user_id)
            self.assertEqual(migration.reports[0].user_id, self.user_id)

            db.session.add(MigrationFile(migration_id=migration.id, object_key="one"))
            with self.assertRaises(IntegrityError):
                db.session.commit()
            db.session.rollback()

            db.session.add(Report(report_id="another-report", user_id=self.user_id, migration_id=migration.id, status="pending"))
            with self.assertRaises(IntegrityError):
                db.session.commit()
            db.session.rollback()

    def test_application_timestamps_use_aware_utc_defaults(self):
        timestamp = utc_now()
        self.assertIsNotNone(timestamp.tzinfo)
        self.assertEqual(timestamp.utcoffset().total_seconds(), 0)
        for model in (User, Migration, MigrationFile, MigrationPlan, Report, AuditEvent):
            for column in model.__table__.columns:
                if column.name.endswith("_at"):
                    self.assertIsInstance(column.type, UTCDateTime, f"{model.__name__}.{column.name} must be UTC-aware")
        with self.app.app_context():
            migration = self._migration("aware-timestamp")
            db.session.add(migration)
            db.session.commit()
            db.session.expire_all()
            persisted = Migration.query.filter_by(migration_id="aware-timestamp").one()
            self.assertIsNotNone(persisted.created_at.tzinfo)
            self.assertEqual(persisted.created_at.utcoffset().total_seconds(), 0)

    def test_no_application_owned_datetime_utcnow_calls_remain(self):
        application_files = list((ROOT / "app").rglob("*.py"))
        offenders = [path.relative_to(ROOT).as_posix() for path in application_files if "datetime.utcnow(" in path.read_text(encoding="utf-8")]
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
