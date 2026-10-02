"""Focused persisted worker, cancellation, and restart-boundary tests."""

import re
import unittest
from datetime import timedelta

from app import create_app
from app.extensions import bcrypt, db
from app.models.migration import Migration
from app.models.user import User
from app.security.audit_logger import AuditEvent
from app.models.report import Report
from app.services import s3_migration_service
from app.services.migration_execution_service import claim_migration, finalize_cancelled, release_claim
from app.utils.time import utc_now


class ExecutionLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True, "SECRET_KEY": "execution-lifecycle-test-secret",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
        })
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()
            self.owner = User(name="Owner", email="worker-owner@example.com",
                              password_hash=bcrypt.generate_password_hash("secure-password-123").decode())
            self.other = User(name="Other", email="worker-other@example.com",
                              password_hash=bcrypt.generate_password_hash("secure-password-456").decode())
            db.session.add_all([self.owner, self.other]); db.session.commit()
            self.owner_id, self.other_id = self.owner.id, self.other.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove(); db.drop_all(); db.engine.dispose()

    def _migration(self, migration_id="lifecycle-one", user_id=None, status="preparing"):
        return Migration(migration_id=migration_id, user_id=user_id or self.owner_id,
                         source_cloud="aws", target_cloud="azure", resource_type="s3",
                         resource_name="bucket", status=status, active_identity=migration_id)

    def _login(self):
        token = self._csrf()
        self.client.post("/login", data={"csrf_token": token, "email": "worker-owner@example.com", "password": "secure-password-123"})

    def _csrf(self):
        response = self.client.get("/")
        return re.search(r'name="csrf-token" content="([^"]+)"', response.get_data(as_text=True)).group(1)

    def test_database_claim_allows_only_one_worker(self):
        with self.app.app_context():
            db.session.add(self._migration()); db.session.commit()
            first = claim_migration("lifecycle-one", "worker-a")
            second = claim_migration("lifecycle-one", "worker-b")
            stored = Migration.query.filter_by(migration_id="lifecycle-one").one()
            self.assertEqual(first, "worker-a")
            self.assertIsNone(second)
            self.assertEqual(stored.worker_token, "worker-a")

    def test_expired_worker_lease_can_be_claimed_for_safe_recovery(self):
        with self.app.app_context():
            migration = self._migration()
            migration.worker_token = "expired-worker"
            migration.lease_expires_at = utc_now() - timedelta(seconds=1)
            db.session.add(migration); db.session.commit()
            claim = claim_migration("lifecycle-one", "recovery-worker")
            stored = Migration.query.filter_by(migration_id="lifecycle-one").one()
            self.assertEqual(claim, "recovery-worker")
            self.assertEqual(stored.worker_token, "recovery-worker")

    def test_stale_token_cannot_clear_newer_claim_or_finalize_state(self):
        with self.app.app_context():
            migration = self._migration(status="running")
            migration.worker_token = "current-worker"
            db.session.add(migration); db.session.commit()
            self.assertFalse(release_claim(migration, "stale-worker"))
            self.assertFalse(finalize_cancelled(migration, "stale-worker"))
            persisted = Migration.query.filter_by(migration_id="lifecycle-one").one()
            self.assertEqual(persisted.status, "running")
            self.assertEqual(persisted.worker_token, "current-worker")

    def test_restart_marks_s3_worker_interrupted_and_releases_lease(self):
        with self.app.app_context():
            migration = self._migration(status="running")
            migration.worker_token = "stale-worker"
            migration.lease_expires_at = utc_now() - timedelta(seconds=1)
            db.session.add(migration); db.session.commit()
            s3_migration_service.mark_incomplete_migrations_interrupted()
            migration = Migration.query.filter_by(migration_id="lifecycle-one").one()
            self.assertEqual(migration.status, "interrupted")
            self.assertIsNone(migration.worker_token)
            self.assertIsNone(migration.lease_expires_at)

    def test_startup_recovery_preserves_live_s3_worker_lease(self):
        with self.app.app_context():
            migration = self._migration(status="running")
            migration.worker_token = "live-worker"
            migration.lease_expires_at = utc_now() + timedelta(minutes=5)
            db.session.add(migration); db.session.commit()
            s3_migration_service.mark_incomplete_migrations_interrupted()
            persisted = Migration.query.filter_by(migration_id="lifecycle-one").one()
            self.assertEqual(persisted.status, "running")
            self.assertEqual(persisted.worker_token, "live-worker")

    def test_startup_recovery_handles_unclaimed_and_is_repeatable(self):
        with self.app.app_context():
            migration = self._migration(status="running")
            migration.worker_token = None
            migration.lease_expires_at = utc_now() + timedelta(minutes=5)
            db.session.add(migration); db.session.commit()
            s3_migration_service.mark_incomplete_migrations_interrupted()
            s3_migration_service.mark_incomplete_migrations_interrupted()
            persisted = Migration.query.filter_by(migration_id="lifecycle-one").one()
            self.assertEqual(persisted.status, "interrupted")
            self.assertIsNone(persisted.worker_token)

    def test_owner_can_cancel_queued_work_and_foreign_owner_cannot(self):
        with self.app.app_context():
            db.session.add(self._migration(status="preparing")); db.session.commit()
            db.session.add(self._migration("foreign", self.other_id)); db.session.commit()
        self._login()
        denied = self.client.post("/api/migrations/foreign/cancel", json={}, headers={"X-CSRFToken": self._csrf()})
        self.assertEqual(denied.status_code, 404)
        cancelled = self.client.post("/api/migrations/lifecycle-one/cancel", json={}, headers={"X-CSRFToken": self._csrf()})
        self.assertEqual(cancelled.status_code, 202)
        self.assertEqual(cancelled.get_json()["status"], "cancelled")
        with self.app.app_context():
            migration = Migration.query.filter_by(migration_id="lifecycle-one").one()
            self.assertEqual(migration.status, "cancelled")
            self.assertTrue(migration.cancellation_requested)
            self.assertIsNone(migration.active_identity)
            self.assertIsNotNone(AuditEvent.query.filter_by(
                event="migration_cancellation_requested", migration_id="lifecycle-one"
            ).first())
            self.assertEqual(Report.query.filter_by(migration_id=migration.id).count(), 1)

    def test_cancellation_requires_authenticated_csrf_protected_route(self):
        with self.app.app_context():
            db.session.add(self._migration()); db.session.commit()
        self.assertEqual(self.client.post("/api/migrations/lifecycle-one/cancel", json={}).status_code, 401)
        self._login()
        self.assertEqual(self.client.post("/api/migrations/lifecycle-one/cancel", json={}).status_code, 400)

    def test_terminal_migration_cannot_be_cancelled_or_reclaimed(self):
        with self.app.app_context():
            db.session.add(self._migration(status="completed")); db.session.commit()
            self.assertIsNone(claim_migration("lifecycle-one", "new-worker"))
        self._login()
        response = self.client.post("/api/migrations/lifecycle-one/cancel", json={}, headers={"X-CSRFToken": self._csrf()})
        self.assertEqual(response.status_code, 400)

    def test_report_get_does_not_create_a_report_for_legacy_execution(self):
        with self.app.app_context():
            db.session.add(self._migration(status="interrupted")); db.session.commit()
        self._login()
        response = self.client.get("/api/migrations/lifecycle-one/report")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.get_json()["report_id"])
        with self.app.app_context():
            self.assertEqual(Report.query.filter_by(migration_id=Migration.query.filter_by(migration_id="lifecycle-one").one().id).count(), 0)


if __name__ == "__main__":
    unittest.main()
