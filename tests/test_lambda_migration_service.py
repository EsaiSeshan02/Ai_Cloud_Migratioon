import io
import unittest
import zipfile
from unittest.mock import Mock, patch
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.extensions import db
from app.models.user import User
from app.models.migration import Migration
from app.models.migration import MigrationPlan, MigrationPlanResource
from app.services import lambda_migration_service as service
from app.services.migration_plan_service import approve_lambda_execution_target
from app.services.report_service import build_report_payload, generate_report, serialize_report


class LambdaMigrationServiceTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({"TESTING": True, "SECRET_KEY": "test-secret", "SQLALCHEMY_DATABASE_URI": "sqlite://", "WTF_CSRF_ENABLED": False})
        with self.app.app_context():
            db.create_all()
            user = User(name="Lambda", email="lambda@example.com", password_hash="hash")
            db.session.add(user); db.session.commit()
            self.user_id = user.id

    def tearDown(self):
        with self.app.app_context(): db.session.remove(); db.drop_all(); db.engine.dispose()

    def test_details_exclude_environment_values(self):
        client = Mock(); client.get_function.return_value = {"Code": {"Location": "https://signed.example/package"}, "Configuration": {
            "FunctionArn": "arn:aws:lambda:region:account:function:demo", "FunctionName": "demo", "Runtime": "python3.11",
            "Handler": "handler.main", "PackageType": "Zip", "Environment": {"Variables": {"PASSWORD": "secret"}}, "VpcConfig": {}}}
        client.get_paginator.return_value.paginate.return_value = [{"EventSourceMappings": []}]
        session = Mock(); session.client.return_value = client
        details = service.get_lambda_details(session, "demo")
        self.assertTrue(details["success"]); self.assertEqual(details["environment_names"], ["PASSWORD"])
        self.assertNotIn("secret", str(details))

    def test_assessment_rejects_container_layers_vpc_and_events(self):
        outcome = service.assess_lambda({"runtime": "python3.12", "package_type": "Image", "handler": "bad",
                                         "layers": ["layer"], "vpc_enabled": True, "event_sources": ["arn"]})
        self.assertEqual(outcome["classification"], "manual_review_required")

    def test_package_path_traversal_is_rejected(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive: archive.writestr("../escape.py", "x")
        response = Mock(); response.iter_content.return_value = [payload.getvalue()]; response.raise_for_status.return_value = None
        with patch("app.services.lambda_migration_service.requests.get", return_value=response):
            with self.assertRaises(ValueError): service._download_and_build_package("https://signed.example/package", "handler.main")

    def test_target_validation_rejects_missing_target_without_azure_call(self):
        result = service.validate_target({"credential": object(), "subscription_id": "sub"}, {})
        self.assertFalse(result["success"])
        self.assertIn("required", result["message"])

    def test_invalid_target_configuration_is_rejected_before_provider_call(self):
        result = service.validate_target({"credential": object(), "subscription_id": "sub"}, {"resource_group": "bad/rg", "function_app_name": "funcapp"})
        self.assertFalse(result["success"])
        self.assertIn("invalid", result["message"])

    def test_success_response_requires_real_deploy_and_management_validation(self):
        target_client = Mock()
        target_client.web_apps.list_publishing_credentials.return_value = Mock(
            publishing_user_name="deployment-user", publishing_password="deployment-password")
        target_client.web_apps.get.return_value = Mock()
        deployed_function = Mock(); deployed_function.name = "migrated_lambda"
        target_client.web_apps.list_functions.return_value = [deployed_function]
        target = {"success": True, "client": target_client, "resource_group": "rg", "function_app_name": "funcapp", "slot": ""}
        details = {"success": True, "function_arn": "arn:aws:lambda:r:a:function:demo", "function_name": "demo",
                   "runtime": "python3.11", "handler": "handler.main", "package_type": "Zip", "layers": [],
                   "vpc_enabled": False, "event_sources": [], "environment_names": [], "code_location": "https://signed.example/package"}
        response = Mock(); response.raise_for_status.return_value = None
        with self.app.app_context(), \
             patch.object(service, "get_lambda_details", return_value=details), \
             patch.object(service, "validate_target", return_value=target), \
             patch.object(service, "_download_and_build_package", return_value=b"real-package-bytes"), \
             patch("app.services.lambda_migration_service.requests.post", return_value=response) as deploy:
            result = service.deploy_lambda(Mock(), {"credential": object(), "subscription_id": "sub"}, "demo", {"resource_group": "rg", "function_app_name": "funcapp"}, self.user_id)
        self.assertTrue(result["success"])
        deploy.assert_called_once()
        target_client.web_apps.get.assert_called_once_with("rg", "funcapp")
        target_client.web_apps.list_functions.assert_called_once_with("rg", "funcapp")
        with self.app.app_context():
            self.assertEqual(Migration.query.filter_by(resource_type="lambda").one().status, "completed")

    def test_aws_specific_package_is_held_for_manual_review(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("handler.py", "import boto3\ndef main(event, context): return {}")
        response = Mock(); response.iter_content.return_value = [payload.getvalue()]; response.raise_for_status.return_value = None
        with patch("app.services.lambda_migration_service.requests.get", return_value=response):
            with self.assertRaises(service.ManualReviewRequired):
                service._download_and_build_package("https://signed.example/package", "handler.main")

    def test_active_deployment_is_reused_before_target_validation(self):
        details = {"success": True, "function_arn": "arn:aws:lambda:r:a:function:demo", "function_name": "demo",
                   "runtime": "python3.11", "handler": "handler.main", "package_type": "Zip", "layers": [],
                   "vpc_enabled": False, "event_sources": [], "environment_names": [], "code_location": "https://signed.example/package"}
        config = {"resource_group": "rg", "function_app_name": "funcapp"}
        identity = service._lambda_identity(self.user_id, details["function_arn"], config)
        with self.app.app_context():
            db.session.add(Migration(migration_id="active-lambda", user_id=self.user_id, active_identity=identity,
                                     source_cloud="aws", target_cloud="azure", resource_type="lambda",
                                     resource_name="demo", status="deploying"))
            db.session.commit()
            with patch.object(service, "get_lambda_details", return_value=details), \
                 patch.object(service, "validate_target") as validate_target:
                result = service.deploy_lambda(Mock(), {}, "demo", config, self.user_id)
        self.assertTrue(result["success"])
        self.assertIn("already active", result["message"])
        validate_target.assert_not_called()

    def test_approved_lambda_target_is_persisted_without_credentials(self):
        with self.app.app_context():
            plan = MigrationPlan(plan_id="lambda-plan", user_id=self.user_id, source_cloud="aws", target_cloud="azure")
            db.session.add(plan); db.session.flush()
            resource = MigrationPlanResource(plan_id=plan.id, source_cloud="aws", target_cloud="azure", service="Lambda",
                                              resource_id="arn:lambda:demo", resource_name="demo", target_service="Azure Functions",
                                              capability_classification="planning_only", compatibility=60, execution_mode="assessment_only",
                                              status="Planning only")
            db.session.add(resource); db.session.commit()
            approve_lambda_execution_target(plan, "demo", {"resource_group": "rg", "function_app_name": "funcapp", "deployment_slot": ""})
            db.session.refresh(resource)
            self.assertIn("approved_lambda_target", resource.recommendation_data)
            self.assertNotIn("credential", resource.recommendation_data.lower())
            self.assertEqual(resource.capability_classification, "planning_only")

    def test_target_validation_failure_is_persisted_without_target_secrets(self):
        details = {"success": True, "function_arn": "arn:aws:lambda:r:a:function:demo", "function_name": "demo",
                   "runtime": "python3.11", "handler": "handler.main", "package_type": "Zip", "layers": [],
                   "vpc_enabled": False, "event_sources": [], "environment_names": [], "code_location": "https://signed.example/package"}
        with self.app.app_context(), patch.object(service, "get_lambda_details", return_value=details), \
             patch.object(service, "validate_target", return_value={"success": False, "message": "credential-value"}):
            result = service.deploy_lambda(Mock(), {"credential": object(), "subscription_id": "sub"}, "demo",
                                           {"resource_group": "rg", "function_app_name": "funcapp"}, self.user_id)
            migration = Migration.query.filter_by(resource_type="lambda").one()
            report = serialize_report(generate_report(migration))["report"]
            # Assert while the ORM instance remains attached; the report itself is
            # deliberately a detached, serializable snapshot.
            self.assertEqual(migration.status, "failed")
            self.assertEqual(migration.failure_reason, "Azure Function App target validation failed.")
        self.assertFalse(result["success"])
        self.assertNotIn("credential-value", str(report))

    def test_kudu_non_success_response_is_a_safe_persisted_failure(self):
        target_client = Mock()
        target_client.web_apps.list_publishing_credentials.return_value = Mock(
            publishing_user_name="deployment-user", publishing_password="deployment-password")
        target = {"success": True, "client": target_client, "resource_group": "rg", "function_app_name": "funcapp", "slot": ""}
        details = {"success": True, "function_arn": "arn:aws:lambda:r:a:function:demo", "function_name": "demo",
                   "runtime": "python3.11", "handler": "handler.main", "package_type": "Zip", "layers": [],
                   "vpc_enabled": False, "event_sources": [], "environment_names": [], "code_location": "https://signed.example/package"}
        rejected = Mock(); rejected.raise_for_status.side_effect = service.requests.HTTPError("provider-secret")
        with self.app.app_context(), patch.object(service, "get_lambda_details", return_value=details), \
             patch.object(service, "validate_target", return_value=target), \
             patch.object(service, "_download_and_build_package", return_value=b"package"), \
             patch("app.services.lambda_migration_service.requests.post", return_value=rejected):
            result = service.deploy_lambda(Mock(), {"credential": object(), "subscription_id": "sub"}, "demo",
                                           {"resource_group": "rg", "function_app_name": "funcapp"}, self.user_id)
            migration = Migration.query.filter_by(resource_type="lambda").one()
        self.assertFalse(result["success"])
        self.assertEqual(migration.failure_reason, "Azure ZIP deployment was rejected by the target service.")
        self.assertNotIn("provider-secret", migration.failure_reason)

    def test_kudu_timeout_is_persisted_and_reported_safely(self):
        target_client = Mock()
        target_client.web_apps.list_publishing_credentials.return_value = Mock(
            publishing_user_name="deployment-user", publishing_password="deployment-password")
        target = {"success": True, "client": target_client, "resource_group": "rg", "function_app_name": "funcapp", "slot": ""}
        details = {"success": True, "function_arn": "arn:aws:lambda:r:a:function:demo", "function_name": "demo",
                   "runtime": "python3.11", "handler": "handler.main", "package_type": "Zip", "layers": [],
                   "vpc_enabled": False, "event_sources": [], "environment_names": [], "code_location": "https://signed.example/package"}
        with self.app.app_context(), patch.object(service, "get_lambda_details", return_value=details), \
             patch.object(service, "validate_target", return_value=target), \
             patch.object(service, "_download_and_build_package", return_value=b"package"), \
             patch("app.services.lambda_migration_service.requests.post", side_effect=service.requests.Timeout("token-value")):
            result = service.deploy_lambda(Mock(), {"credential": object(), "subscription_id": "sub"}, "demo",
                                           {"resource_group": "rg", "function_app_name": "funcapp"}, self.user_id)
            migration = Migration.query.filter_by(resource_type="lambda").one()
            report = build_report_payload(migration)
        self.assertFalse(result["success"])
        self.assertEqual(migration.status, "failed")
        self.assertEqual(migration.failure_reason, "Azure ZIP deployment timed out.")
        self.assertNotIn("token-value", str(report))
        self.assertNotIn("deployment-password", str(report))

    def test_management_validation_failure_never_reports_completed(self):
        target_client = Mock()
        target_client.web_apps.list_publishing_credentials.return_value = Mock(
            publishing_user_name="deployment-user", publishing_password="deployment-password")
        target_client.web_apps.list_functions.return_value = []
        target = {"success": True, "client": target_client, "resource_group": "rg", "function_app_name": "funcapp", "slot": ""}
        details = {"success": True, "function_arn": "arn:aws:lambda:r:a:function:demo", "function_name": "demo",
                   "runtime": "python3.11", "handler": "handler.main", "package_type": "Zip", "layers": [],
                   "vpc_enabled": False, "event_sources": [], "environment_names": [], "code_location": "https://signed.example/package"}
        response = Mock(); response.raise_for_status.return_value = None
        with self.app.app_context(), patch.object(service, "get_lambda_details", return_value=details), \
             patch.object(service, "validate_target", return_value=target), \
             patch.object(service, "_download_and_build_package", return_value=b"package"), \
             patch("app.services.lambda_migration_service.requests.post", return_value=response):
            result = service.deploy_lambda(Mock(), {"credential": object(), "subscription_id": "sub"}, "demo",
                                           {"resource_group": "rg", "function_app_name": "funcapp"}, self.user_id)
            migration = Migration.query.filter_by(resource_type="lambda").one()
        self.assertFalse(result["success"])
        self.assertEqual(migration.status, "failed")
        self.assertNotEqual(migration.status, "completed")

    def test_restart_marks_active_lambda_for_manual_review(self):
        with self.app.app_context():
            db.session.add(Migration(migration_id="interrupted-lambda", user_id=self.user_id, active_identity="identity",
                                     source_cloud="aws", target_cloud="azure", resource_type="lambda",
                                     resource_name="demo", status="deploying"))
            db.session.commit()
            service.mark_incomplete_lambda_migrations_requires_review()
            migration = Migration.query.filter_by(migration_id="interrupted-lambda").one()
        self.assertEqual(migration.status, "manual_review_required")
        self.assertIsNone(migration.active_identity)
        self.assertIn("interrupted", migration.failure_reason)

    def test_database_constraint_prevents_two_active_lambda_records(self):
        with self.app.app_context():
            db.session.add(Migration(migration_id="first-active", user_id=self.user_id, active_identity="shared-lambda-identity",
                                     source_cloud="aws", target_cloud="azure", resource_type="lambda", resource_name="demo", status="deploying"))
            db.session.commit()
            db.session.add(Migration(migration_id="second-active", user_id=self.user_id, active_identity="shared-lambda-identity",
                                     source_cloud="aws", target_cloud="azure", resource_type="lambda", resource_name="demo", status="preparing"))
            with self.assertRaises(IntegrityError):
                db.session.commit()
            db.session.rollback()
            self.assertEqual(Migration.query.filter_by(active_identity="shared-lambda-identity").count(), 1)
