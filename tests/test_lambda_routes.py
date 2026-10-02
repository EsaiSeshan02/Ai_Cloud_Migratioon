import re
import unittest
from unittest.mock import Mock, patch

from app import create_app
from app.extensions import bcrypt, db
from app.models.migration import Migration, MigrationPlan, MigrationPlanResource
from app.models.user import User
from app.security.audit_logger import AuditEvent
from app.services.aws_service import migration_sessions
from app.services.azure_service import azure_sessions
from app.services.lambda_migration_service import _lambda_identity
from app.services.lambda_migration_service import ManualReviewRequired


class LambdaRouteSecurityTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({"TESTING": True, "SECRET_KEY": "test-secret", "SQLALCHEMY_DATABASE_URI": "sqlite://"})
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()
            self.owner = User(name="Owner", email="lambda-owner@example.com", password_hash=bcrypt.generate_password_hash("secure-password-123").decode())
            self.other = User(name="Other", email="lambda-other@example.com", password_hash=bcrypt.generate_password_hash("secure-password-456").decode())
            db.session.add_all([self.owner, self.other]); db.session.commit()
            self.owner_id, self.other_id = self.owner.id, self.other.id
            self.plan_id = self._create_plan(self.owner_id, "owner-lambda-plan")
            self.other_plan_id = self._create_plan(self.other_id, "other-lambda-plan")
        migration_sessions["lambda-aws"] = {"user_id": self.owner_id, "aws_session": Mock(), "created_at": __import__("time").time(), "target": "azure"}
        azure_sessions["lambda-azure"] = {"user_id": self.owner_id, "credential": object(), "subscription_id": "sub", "role": "target"}

    def tearDown(self):
        migration_sessions.clear(); azure_sessions.clear()
        with self.app.app_context():
            db.session.remove(); db.drop_all(); db.engine.dispose()

    def _create_plan(self, user_id, plan_id):
        plan = MigrationPlan(plan_id=plan_id, user_id=user_id, source_cloud="aws", target_cloud="azure")
        db.session.add(plan); db.session.flush()
        db.session.add(MigrationPlanResource(plan_id=plan.id, source_cloud="aws", target_cloud="azure", service="Lambda",
            resource_id="arn:aws:lambda:r:a:function:demo", resource_name="demo", target_service="Azure Functions",
            capability_classification="planning_only", compatibility=60, execution_mode="assessment_only", status="Planning only"))
        db.session.commit()
        return plan.plan_id

    def _login_owner(self):
        self.client.post("/login", data={"csrf_token": self._csrf(), "email": "lambda-owner@example.com", "password": "secure-password-123"})

    def _csrf(self):
        response = self.client.get("/")
        return re.search(r'name="csrf-token" content="([^"]+)"', response.get_data(as_text=True)).group(1)

    def _payload(self, plan_id=None, configuration=None):
        return {"source_session_id": "lambda-aws", "target_session_id": "lambda-azure", "function_name": "demo",
                "plan_id": plan_id or self.plan_id,
                "configuration": configuration or {"resource_group": "rg", "function_app_name": "funcapp"}}

    def test_unauthenticated_lambda_start_is_rejected(self):
        response = self.client.post("/api/migration/lambda/start", json=self._payload())
        self.assertEqual(response.status_code, 401)

    def test_authenticated_lambda_start_requires_csrf(self):
        self._login_owner()
        response = self.client.post("/api/migration/lambda/start", json=self._payload())
        self.assertEqual(response.status_code, 400)

    def test_plan_ownership_is_enforced(self):
        self._login_owner()
        response = self.client.post("/api/migration/lambda/start", json=self._payload(self.other_plan_id), headers={"X-CSRFToken": self._csrf()})
        self.assertEqual(response.status_code, 403)

    def test_invalid_target_is_rejected_before_provider_mutation(self):
        self._login_owner()
        with patch("app.services.lambda_migration_service.deploy_lambda") as deploy:
            response = self.client.post("/api/migration/lambda/start", json=self._payload(configuration={"resource_group": "bad/rg", "function_app_name": "funcapp"}), headers={"X-CSRFToken": self._csrf()})
        self.assertEqual(response.status_code, 400)
        deploy.assert_not_called()

    def test_safe_provider_failure_response_contains_no_secrets(self):
        self._login_owner()
        failure = {"success": False, "migration_id": "lambda-failed", "status": "failed", "message": "Lambda deployment failed."}
        with patch("app.services.lambda_migration_service.deploy_lambda", return_value=failure):
            response = self.client.post("/api/migration/lambda/start", json=self._payload(), headers={"X-CSRFToken": self._csrf()})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("credential", response.get_data(as_text=True).lower())
        self.assertNotIn("secret", response.get_data(as_text=True).lower())
        with self.app.app_context():
            audit = AuditEvent.query.filter_by(event="lambda_migration_not_started", migration_id="lambda-failed").one()
            self.assertEqual(audit.status, "failed")

    def test_foreign_cloud_session_is_rejected_before_lambda_provider_use(self):
        self._login_owner()
        migration_sessions["lambda-aws"]["user_id"] = self.other_id
        with patch("app.services.lambda_migration_service.deploy_lambda") as deploy:
            response = self.client.post("/api/migration/lambda/start", json=self._payload(), headers={"X-CSRFToken": self._csrf()})
        self.assertEqual(response.status_code, 403)
        deploy.assert_not_called()

    def test_unsupported_package_is_manual_review_before_kudu_deployment(self):
        self._login_owner()
        target = {"success": True, "client": Mock(), "resource_group": "rg", "function_app_name": "funcapp", "slot": ""}
        details = {"success": True, "function_arn": "arn:aws:lambda:r:a:function:demo", "function_name": "demo", "runtime": "python3.11",
                   "handler": "handler.main", "package_type": "Zip", "layers": [], "vpc_enabled": False, "event_sources": [], "environment_names": [],
                   "code_location": "https://signed.example/package"}
        with patch("app.services.lambda_migration_service.get_lambda_details", return_value=details), \
             patch("app.services.lambda_migration_service.validate_target", return_value=target), \
             patch("app.services.lambda_migration_service._download_and_build_package", side_effect=ManualReviewRequired("AWS SDK requires review")), \
             patch("app.services.lambda_migration_service.requests.post") as deploy:
            response = self.client.post("/api/migration/lambda/start", json=self._payload(), headers={"X-CSRFToken": self._csrf()})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["status"], "manual_review_required")
        deploy.assert_not_called()
        with self.app.app_context():
            self.assertEqual(Migration.query.filter_by(resource_type="lambda").one().status, "manual_review_required")

    def test_active_lambda_is_idempotent_through_route_boundary(self):
        self._login_owner()
        details = {"success": True, "function_arn": "arn:aws:lambda:r:a:function:demo", "function_name": "demo", "runtime": "python3.11",
                   "handler": "handler.main", "package_type": "Zip", "layers": [], "vpc_enabled": False, "event_sources": [], "environment_names": []}
        identity = _lambda_identity(self.owner_id, details["function_arn"], self._payload()["configuration"])
        with self.app.app_context():
            db.session.add(Migration(migration_id="lambda-active", user_id=self.owner_id, active_identity=identity, source_cloud="aws",
                                     target_cloud="azure", resource_type="lambda", resource_name="demo", status="deploying")); db.session.commit()
        with patch("app.services.lambda_migration_service.get_lambda_details", return_value=details), \
             patch("app.services.lambda_migration_service.validate_target") as validate_target:
            response = self.client.post("/api/migration/lambda/start", json=self._payload(), headers={"X-CSRFToken": self._csrf()})
        self.assertEqual(response.status_code, 202)
        self.assertIn("already active", response.get_json()["message"])
        validate_target.assert_not_called()
        with self.app.app_context():
            self.assertEqual(Migration.query.filter_by(resource_type="lambda").count(), 1)

    def test_uncertain_lambda_route_blocks_start_until_explicit_resolution(self):
        self._login_owner()
        details = {"success": True, "function_arn": "arn:aws:lambda:r:a:function:demo", "function_name": "demo", "runtime": "python3.11",
                   "handler": "handler.main", "package_type": "Zip", "layers": [], "vpc_enabled": False, "event_sources": [], "environment_names": []}
        identity = _lambda_identity(self.owner_id, details["function_arn"], self._payload()["configuration"])
        with self.app.app_context():
            db.session.add(Migration(migration_id="uncertain-route", user_id=self.owner_id, active_identity=identity,
                                     source_cloud="aws", target_cloud="azure", resource_type="lambda", resource_name="demo",
                                     status="manual_review_required", uncertain_external_operation=True))
            db.session.commit()
        with patch("app.services.lambda_migration_service.get_lambda_details", return_value=details), \
             patch("app.services.lambda_migration_service.requests.post") as kudu:
            blocked = self.client.post("/api/migration/lambda/start", json=self._payload(), headers={"X-CSRFToken": self._csrf()})
        self.assertEqual(blocked.status_code, 400)
        self.assertEqual(blocked.get_json()["status"], "manual_review_required")
        kudu.assert_not_called()
        resolved = self.client.post(
            "/api/migration/lambda/uncertain-route/resolve-uncertain",
            json={"confirmation": "target_inspected_no_active_deployment"},
            headers={"X-CSRFToken": self._csrf()},
        )
        self.assertEqual(resolved.status_code, 200)
        self.assertEqual(resolved.get_json()["status"], "manual_review_required")


if __name__ == "__main__":
    unittest.main()
