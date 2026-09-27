"""UI/route smoke tests for the truthful supported-capability workflow.

These tests intentionally inspect only local templates, route registration, and
the authenticated page boundary. They do not call any cloud provider.
"""

import re
import time
import unittest
from pathlib import Path

from app import create_app
from app.extensions import bcrypt, db
from app.models.user import User
from app.services.aws_service import migration_sessions
from app.services.azure_service import azure_sessions


ROOT = Path(__file__).resolve().parents[1]


class DemoTruthfulnessTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-only-demo-truthfulness-key",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "SESSION_COOKIE_SECURE": False,
        })
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()
            user = User(
                name="Demo Owner",
                email="demo-owner@example.com",
                password_hash=bcrypt.generate_password_hash("secure-password-123").decode(),
            )
            db.session.add(user)
            db.session.commit()
            self.user_id = user.id
        migration_sessions["demo-aws"] = {
            "user_id": self.user_id,
            "created_at": time.time(),
            "target": "azure",
        }
        azure_sessions["demo-azure"] = {"user_id": self.user_id, "role": "target"}

    def tearDown(self):
        migration_sessions.clear()
        azure_sessions.clear()
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def _csrf(self):
        response = self.client.get("/")
        return re.search(r'name="csrf-token" content="([^"]+)"', response.get_data(as_text=True)).group(1)

    def _login(self):
        response = self.client.post("/login", data={
            "csrf_token": self._csrf(),
            "email": "demo-owner@example.com",
            "password": "secure-password-123",
        })
        self.assertEqual(response.status_code, 302)

    def test_active_dashboard_configuration_and_history_pages_render_for_owned_sessions(self):
        self.assertEqual(self.client.get("/migration/dashboard").status_code, 302)
        self._login()
        dashboard = self.client.get(
            "/migration/dashboard?source=aws&target=azure"
            "&source_session_id=demo-aws&target_session_id=demo-azure"
        )
        configure = self.client.get(
            "/migration/configure?source=aws&target=azure"
            "&source_session_id=demo-aws&target_session_id=demo-azure"
        )
        history = self.client.get("/migration/history")
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(configure.status_code, 200)
        self.assertEqual(history.status_code, 200)
        self.assertIn("Scan Source Infrastructure", dashboard.get_data(as_text=True))
        self.assertIn("Planning / Manual Review Required", configure.get_data(as_text=True))
        self.assertIn("PERSISTED EXECUTION HISTORY", history.get_data(as_text=True))

    def test_only_supported_execution_routes_are_registered(self):
        rules = {rule.rule for rule in self.app.url_map.iter_rules()}
        self.assertIn("/api/migration/s3/start", rules)
        self.assertIn("/api/migration/lambda/start", rules)
        self.assertFalse(any("ec2" in rule.lower() or "rds" in rule.lower() or "dynamodb" in rule.lower()
                             for rule in rules if rule.startswith("/api/migration/")))
        self.assertFalse(any(rule in {"/dashboard", "/upload", "/report", "/migration/report"} for rule in rules))

    def test_gcp_cannot_open_a_connected_target_or_dashboard_workflow(self):
        self._login()
        connect = self.client.get(
            "/migration/connect-cloud?source=aws&target=gcp&source_session_id=demo-aws"
        )
        dashboard = self.client.get(
            "/migration/dashboard?source=aws&target=gcp"
            "&source_session_id=demo-aws&target_session_id=not-a-session"
        )
        self.assertEqual(connect.status_code, 400)
        self.assertEqual(dashboard.status_code, 400)
        self.assertIn("GCP connection, assessment, and execution are not implemented", connect.get_data(as_text=True))

        boundary = self.client.get("/migration/gcp-source?target=aws")
        body = boundary.get_data(as_text=True)
        self.assertEqual(boundary.status_code, 200)
        self.assertIn("Google Cloud Is Not Available", body)
        self.assertIn('id="gcp-service-account"', body)
        self.assertRegex(body, r'id="gcp-service-account"[\s\S]*?disabled')

    def test_configuration_assets_hide_execution_controls_for_planning_resources(self):
        script = (ROOT / "app" / "static" / "js" / "configure-migration.js").read_text(encoding="utf-8")
        template = (ROOT / "app" / "templates" / "migration" / "configure-migration.html").read_text(encoding="utf-8")
        active_dashboard = (ROOT / "app" / "templates" / "migration" / "dashboard-migration.html").read_text(encoding="utf-8")
        self.assertIn('if (service === "S3") return "s3";', script)
        self.assertIn('if (service === "LAMBDA") return "lambda";', script)
        self.assertIn('startButton.hidden = path === "planning";', script)
        self.assertNotIn("startEC2Migration", script)
        self.assertIn("data-s3-target", template)
        self.assertIn("data-lambda-target", template)
        self.assertIn("planning-only-notice", template)
        self.assertIn("js/migration-dashboard.js", active_dashboard)
        self.assertFalse((ROOT / "app" / "static" / "js" / "dashboard-migration.js").exists())


if __name__ == "__main__":
    unittest.main()
