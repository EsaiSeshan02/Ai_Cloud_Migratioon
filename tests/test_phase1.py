import re
import unittest

from app import create_app
from app.extensions import bcrypt, db
from app.models.migration import Migration, MigrationFile
from app.models.user import User
from app.security.logging_utils import RedactingFilter
from app.services.aws_service import migration_sessions
from app.services.azure_service import azure_sessions


class PhaseOneSecurityTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-only-secret-key-not-used-in-production",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "WTF_CSRF_TIME_LIMIT": None,
            "SESSION_COOKIE_SECURE": False,
        })
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def csrf_token(self, path="/"):
        response = self.client.get(path)
        match = re.search(r'name="csrf-token" content="([^"]+)"', response.get_data(as_text=True))
        self.assertIsNotNone(match)
        return match.group(1)

    def register(self, email="owner@example.com", password="secure-password-123"):
        token = self.csrf_token("/register")
        return self.client.post("/register", data={
            "csrf_token": token,
            "fullname": "Migration Owner",
            "email": email,
            "password": password,
            "confirm_password": password,
        }, follow_redirects=False)

    def test_registration_hashes_password_and_login_logout_work(self):
        response = self.register()
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            user = User.query.filter_by(email="owner@example.com").one()
            self.assertNotEqual(user.password_hash, "secure-password-123")
            self.assertTrue(bcrypt.check_password_hash(user.password_hash, "secure-password-123"))

        token = self.csrf_token("/")
        response = self.client.post("/logout", data={"csrf_token": token}, follow_redirects=False)
        self.assertEqual(response.status_code, 302)

        token = self.csrf_token("/login")
        response = self.client.post("/login", data={
            "csrf_token": token,
            "email": "owner@example.com",
            "password": "secure-password-123",
        }, follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)

    def test_registration_rejects_duplicate_email(self):
        self.assertEqual(self.register().status_code, 302)
        self.client.post("/logout", data={"csrf_token": self.csrf_token("/")})
        response = self.register()
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("already exists", response.get_data(as_text=True).lower())

    def test_sensitive_api_requires_authentication_before_csrf(self):
        response = self.client.post("/api/aws/scan", json={})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["message"], "Please sign in to continue.")

    def test_authenticated_api_rejects_missing_csrf(self):
        self.register()
        response = self.client.post("/api/aws/scan", json={})
        self.assertEqual(response.status_code, 400)
        self.assertIn("form session expired", response.get_json()["message"].lower())

    def test_migration_status_is_scoped_to_owner(self):
        self.register()
        with self.app.app_context():
            owner = User.query.filter_by(email="owner@example.com").one()
            other = User(
                name="Other User",
                email="other@example.com",
                password_hash=bcrypt.generate_password_hash("another-secure-password").decode(),
            )
            db.session.add(other)
            db.session.commit()
            mine = Migration(
                migration_id="mine-001", user_id=owner.id, source_cloud="aws", target_cloud="azure",
                resource_type="s3", resource_name="mine", status="pending",
            )
            theirs = Migration(
                migration_id="theirs-001", user_id=other.id, source_cloud="aws", target_cloud="azure",
                resource_type="s3", resource_name="theirs", status="pending",
            )
            db.session.add_all([mine, theirs])
            db.session.commit()
            db.session.add(MigrationFile(
                migration_id=mine.id, object_key="private-object-key", size_bytes=7,
                status="verified", bytes_transferred=7,
            ))
            db.session.commit()

        self.assertEqual(self.client.get("/api/migrations/mine-001").status_code, 200)
        self.assertEqual(self.client.get("/api/migrations/theirs-001").status_code, 403)
        report = self.client.get("/api/migrations/mine-001/report")
        self.assertEqual(report.status_code, 200)
        self.assertNotIn("private-object-key", report.get_data(as_text=True))
        self.assertEqual(self.client.get("/api/migrations/theirs-001/report").status_code, 403)

        # The Phase 2 retry control must apply the same ownership boundary
        # before it considers cloud session IDs or starts a worker.
        response = self.client.post(
            "/api/migrations/theirs-001/resume",
            json={},
            headers={"X-CSRFToken": self.csrf_token("/")},
        )
        self.assertEqual(response.status_code, 403)

    def test_cloud_session_is_scoped_to_owner_without_calling_aws(self):
        self.register()
        migration_sessions["foreign-session"] = {
            "user_id": 999999,
            "created_at": __import__("time").time(),
            "target": "azure",
        }
        try:
            response = self.client.post(
                "/api/aws/scan",
                json={"session_id": "foreign-session", "target": "azure"},
                headers={"X-CSRFToken": self.csrf_token("/")},
            )
            self.assertEqual(response.status_code, 403)
        finally:
            migration_sessions.pop("foreign-session", None)

    def test_migration_configuration_page_requires_owned_sessions(self):
        self.register()
        with self.app.app_context():
            owner_id = User.query.filter_by(email="owner@example.com").one().id
        migration_sessions["foreign-aws"] = {
            "user_id": 999999,
            "created_at": __import__("time").time(),
            "target": "azure",
        }
        azure_sessions["owned-azure"] = {"user_id": owner_id, "role": "target"}
        try:
            response = self.client.get(
                "/migration/configure?source=aws&target=azure"
                "&source_session_id=foreign-aws&target_session_id=owned-azure"
            )
            self.assertEqual(response.status_code, 403)
        finally:
            migration_sessions.pop("foreign-aws", None)
            azure_sessions.pop("owned-azure", None)

    def test_error_handlers_and_single_aws_scan_route(self):
        self.assertEqual(self.client.get("/not-found").status_code, 404)
        response = self.client.get("/api/not-found")
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.get_json()["success"])
        rules = [rule for rule in self.app.url_map.iter_rules() if rule.rule == "/api/aws/scan"]
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].endpoint, "migration.aws_scan")

    def test_log_filter_redacts_secret_values(self):
        record = __import__("logging").LogRecord(
            "test", 20, __file__, 1, "access_key=ABC secret=DEF password=GHI", (), None
        )
        RedactingFilter().filter(record)
        self.assertNotIn("ABC", record.msg)
        self.assertNotIn("DEF", record.msg)
        self.assertNotIn("GHI", record.msg)

        quoted = __import__("logging").LogRecord(
            "test", 20, __file__, 1,
            '"client_secret": "VALUE" "subscription_id": "SUB"', (), None,
        )
        RedactingFilter().filter(quoted)
        self.assertNotIn("VALUE", quoted.msg)
        self.assertNotIn("SUB", quoted.msg)


if __name__ == "__main__":
    unittest.main()
