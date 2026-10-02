import io
import unittest
import zipfile
from datetime import timedelta
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
from app.utils.time import utc_now


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

    def test_report_failure_does_not_rewrite_lambda_success(self):
        target_client = Mock()
        target_client.web_apps.list_publishing_credentials.return_value = Mock(
            publishing_user_name="deployment-user", publishing_password="deployment-password")
        target_client.web_apps.get.return_value = Mock()
        deployed_function = Mock(); deployed_function.name = "migrated_lambda"
        target_client.web_apps.list_functions.return_value = [deployed_function]
        target = {"success": True, "client": target_client, "resource_group": "rg", "function_app_name": "funcapp", "slot": ""}
        details = {"success": True, "function_arn": "arn:aws:lambda:r:a:function:report-demo", "function_name": "report-demo",
                   "runtime": "python3.11", "handler": "handler.main", "package_type": "Zip", "layers": [],
                   "vpc_enabled": False, "event_sources": [], "environment_names": [], "code_location": "https://signed.example/package"}
        response = Mock(); response.raise_for_status.return_value = None
        with self.app.app_context(), \
             patch.object(service, "get_lambda_details", return_value=details), \
             patch.object(service, "validate_target", return_value=target), \
             patch.object(service, "_download_and_build_package", return_value=b"real-package-bytes"), \
             patch("app.services.lambda_migration_service.requests.post", return_value=response), \
             patch("app.services.report_service.generate_report", side_effect=RuntimeError("report store unavailable")):
            result = service.deploy_lambda(Mock(), {"credential": object(), "subscription_id": "sub"}, "report-demo",
                                           {"resource_group": "rg", "function_app_name": "funcapp"}, self.user_id)
            persisted = Migration.query.filter_by(resource_type="lambda").one()
        self.assertTrue(result["success"])
        self.assertEqual(persisted.status, "completed")

    def test_report_failure_does_not_rewrite_lambda_manual_review(self):
        details = {"success": True, "function_arn": "arn:aws:lambda:r:a:function:review-demo", "function_name": "review-demo",
                   "runtime": "python3.11", "handler": "handler.main", "package_type": "Zip", "layers": [],
                   "vpc_enabled": False, "event_sources": [], "environment_names": [], "code_location": "https://signed.example/package"}
        with self.app.app_context(), \
             patch.object(service, "get_lambda_details", return_value=details), \
             patch.object(service, "validate_target", return_value={"success": True, "client": Mock(), "resource_group": "rg", "function_app_name": "funcapp", "slot": ""}), \
             patch.object(service, "_download_and_build_package", side_effect=service.ManualReviewRequired("unsupported package")), \
             patch("app.services.report_service.generate_report", side_effect=RuntimeError("report store unavailable")):
            result = service.deploy_lambda(Mock(), {"credential": object(), "subscription_id": "sub"}, "review-demo",
                                           {"resource_group": "rg", "function_app_name": "funcapp"}, self.user_id)
            persisted = Migration.query.filter_by(resource_type="lambda").one()
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "manual_review_required")
        self.assertEqual(persisted.status, "manual_review_required")

    def test_report_failure_does_not_rewrite_lambda_provider_failure(self):
        target = {"success": True, "client": Mock(), "resource_group": "rg", "function_app_name": "funcapp", "slot": ""}
        target["client"].web_apps.list_publishing_credentials.return_value = Mock(
            publishing_user_name="deployment-user", publishing_password="deployment-password")
        details = {"success": True, "function_arn": "arn:aws:lambda:r:a:function:failed-report", "function_name": "failed-report",
                   "runtime": "python3.11", "handler": "handler.main", "package_type": "Zip", "layers": [],
                   "vpc_enabled": False, "event_sources": [], "environment_names": [], "code_location": "https://signed.example/package"}
        with self.app.app_context(), \
             patch.object(service, "get_lambda_details", return_value=details), \
             patch.object(service, "validate_target", return_value=target), \
             patch.object(service, "_download_and_build_package", return_value=b"real-package-bytes"), \
             patch("app.services.lambda_migration_service.requests.post", side_effect=service.requests.HTTPError("provider rejected")), \
             patch("app.services.report_service.generate_report", side_effect=RuntimeError("report store unavailable")):
            result = service.deploy_lambda(Mock(), {"credential": object(), "subscription_id": "sub"}, "failed-report",
                                           {"resource_group": "rg", "function_app_name": "funcapp"}, self.user_id)
            persisted = Migration.query.filter_by(resource_type="lambda").one()
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(persisted.status, "failed")

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

    def test_stale_lambda_worker_cannot_persist_after_claim_was_cleared(self):
        with self.app.app_context():
            migration = Migration(migration_id="stale-lambda-worker", user_id=self.user_id,
                                  source_cloud="aws", target_cloud="azure", resource_type="lambda",
                                  resource_name="demo", status="manual_review_required", worker_token=None,
                                  failure_reason="restart recovery")
            db.session.add(migration); db.session.commit()
            result = service._persist_lambda_outcome(
                migration.migration_id, "completed", None, worker_token="old-worker-token"
            )
            persisted = Migration.query.filter_by(migration_id=migration.migration_id).one()
            self.assertIsNone(result)
            self.assertEqual(persisted.status, "manual_review_required")
            self.assertIsNone(persisted.worker_token)
            self.assertEqual(persisted.failure_reason, "restart recovery")

    def test_stale_lambda_worker_cannot_clear_newer_worker_claim(self):
        from app.services.migration_execution_service import release_claim
        with self.app.app_context():
            migration = Migration(migration_id="newer-lambda-worker", user_id=self.user_id,
                                  source_cloud="aws", target_cloud="azure", resource_type="lambda",
                                  resource_name="demo", status="deploying", worker_token="current-token")
            db.session.add(migration); db.session.commit()
            migration_id = migration.id
            self.assertFalse(release_claim(migration, "stale-token"))
            persisted = Migration.query.get(migration_id)
            self.assertEqual(persisted.worker_token, "current-token")

    def test_expired_lambda_lease_does_not_allow_duplicate_kudu_deployment(self):
        target_client = Mock()
        target_client.web_apps.list_publishing_credentials.return_value = Mock(
            publishing_user_name="deployment-user", publishing_password="deployment-password")
        target_client.web_apps.get.return_value = Mock()
        deployed_function = Mock(); deployed_function.name = "migrated_lambda"
        target_client.web_apps.list_functions.return_value = [deployed_function]
        target = {"success": True, "client": target_client, "resource_group": "rg",
                  "function_app_name": "funcapp", "slot": ""}
        details = {"success": True, "function_arn": "arn:aws:lambda:r:a:function:lease-demo",
                   "function_name": "lease-demo", "runtime": "python3.11", "handler": "handler.main",
                   "package_type": "Zip", "layers": [], "vpc_enabled": False, "event_sources": [],
                   "environment_names": [], "code_location": "https://signed.example/package"}
        response = Mock(); response.raise_for_status.return_value = None
        config = {"resource_group": "rg", "function_app_name": "funcapp"}

        def expire_lease_during_kudu(*_args, **_kwargs):
            with self.app.app_context():
                migration = Migration.query.filter_by(resource_type="lambda").one()
                migration.lease_expires_at = utc_now() - timedelta(seconds=1)
                db.session.commit()
            duplicate = service.deploy_lambda(Mock(), {}, "lease-demo", config, self.user_id)
            self.assertTrue(duplicate["success"])
            self.assertIn("already active", duplicate["message"])
            return response

        with self.app.app_context(), \
             patch.object(service, "get_lambda_details", return_value=details), \
             patch.object(service, "validate_target", return_value=target), \
             patch.object(service, "_download_and_build_package", return_value=b"package"), \
             patch("app.services.lambda_migration_service.requests.post", side_effect=expire_lease_during_kudu) as deploy:
            result = service.deploy_lambda(Mock(), {"credential": object(), "subscription_id": "sub"},
                                           "lease-demo", config, self.user_id)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "manual_review_required")
        self.assertEqual(deploy.call_count, 1)
        with self.app.app_context():
            persisted = Migration.query.filter_by(resource_type="lambda").one()
            self.assertEqual(persisted.status, "manual_review_required")
            self.assertTrue(persisted.uncertain_external_operation)
            self.assertIsNotNone(persisted.active_identity)

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
        self.assertEqual(migration.active_identity, "identity")
        self.assertTrue(migration.uncertain_external_operation)
        self.assertIn("interrupted", migration.failure_reason)

    def test_uncertain_lambda_identity_blocks_new_deployment_after_recovery(self):
        details = {"success": True, "function_arn": "arn:aws:lambda:r:a:function:demo", "function_name": "demo",
                   "runtime": "python3.11", "handler": "handler.main", "package_type": "Zip", "layers": [],
                   "vpc_enabled": False, "event_sources": [], "environment_names": [], "code_location": "https://signed.example/package"}
        config = {"resource_group": "rg", "function_app_name": "funcapp"}
        identity = service._lambda_identity(self.user_id, details["function_arn"], config)
        with self.app.app_context():
            db.session.add(Migration(migration_id="uncertain-lambda", user_id=self.user_id, active_identity=identity,
                                     source_cloud="aws", target_cloud="azure", resource_type="lambda", resource_name="demo",
                                     status="deploying", worker_token="old-worker"))
            db.session.commit()
            service.mark_incomplete_lambda_migrations_requires_review()
            with patch.object(service, "get_lambda_details", return_value=details), \
                 patch("app.services.lambda_migration_service.requests.post") as kudu:
                result = service.deploy_lambda(Mock(), {"credential": object(), "subscription_id": "sub"}, "demo", config, self.user_id)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "manual_review_required")
        kudu.assert_not_called()

    def test_uncertain_lambda_blocker_can_only_be_explicitly_resolved(self):
        from app.services.lambda_migration_service import resolve_uncertain_lambda
        with self.app.app_context():
            migration = Migration(migration_id="resolve-lambda", user_id=self.user_id, active_identity="identity",
                                  source_cloud="aws", target_cloud="azure", resource_type="lambda", resource_name="demo",
                                  status="manual_review_required", uncertain_external_operation=True)
            db.session.add(migration); db.session.commit()
            self.assertFalse(resolve_uncertain_lambda(migration, "force_retry"))
            self.assertTrue(resolve_uncertain_lambda(migration, "target_inspected_no_active_deployment"))
            persisted = Migration.query.filter_by(migration_id="resolve-lambda").one()
        self.assertIsNone(persisted.active_identity)
        self.assertFalse(persisted.uncertain_external_operation)
        self.assertEqual(persisted.status, "manual_review_required")

    def test_stale_worker_cannot_change_state_after_uncertain_resolution_and_fresh_claim(self):
        """A late pre-restart worker cannot affect the fresh post-resolution attempt."""
        from app.services.lambda_migration_service import resolve_uncertain_lambda
        from app.services.migration_execution_service import claim_migration, release_claim

        with self.app.app_context():
            original = Migration(
                migration_id="uncertain-original",
                user_id=self.user_id,
                active_identity="lambda-identity",
                source_cloud="aws",
                target_cloud="azure",
                resource_type="lambda",
                resource_name="demo",
                status="deploying",
                worker_token="original-worker-token",
            )
            db.session.add(original)
            db.session.commit()

            service.mark_incomplete_lambda_migrations_requires_review()
            db.session.refresh(original)
            self.assertTrue(original.uncertain_external_operation)
            self.assertEqual(original.active_identity, "lambda-identity")
            self.assertIsNone(original.worker_token)

            self.assertTrue(resolve_uncertain_lambda(
                original, "target_inspected_no_active_deployment"
            ))
            db.session.refresh(original)
            self.assertFalse(original.uncertain_external_operation)
            self.assertIsNone(original.active_identity)

            fresh = Migration(
                migration_id="fresh-approved-attempt",
                user_id=self.user_id,
                active_identity="lambda-identity",
                source_cloud="aws",
                target_cloud="azure",
                resource_type="lambda",
                resource_name="demo",
                status="preparing",
            )
            db.session.add(fresh)
            db.session.commit()
            fresh_token = claim_migration(
                fresh.migration_id,
                worker_token="fresh-worker-token",
                allowed_statuses={"preparing"},
                reclaim_expired=False,
            )
            self.assertEqual(fresh_token, "fresh-worker-token")

            # The old worker can neither record an outcome for its resolved
            # migration nor release the newer attempt's persisted claim.
            self.assertIsNone(service._persist_lambda_outcome(
                original.migration_id,
                "completed",
                worker_token="original-worker-token",
            ))
            self.assertFalse(release_claim(original, "original-worker-token"))
            self.assertFalse(release_claim(fresh, "original-worker-token"))

            db.session.expire_all()
            persisted_original = Migration.query.filter_by(
                migration_id="uncertain-original"
            ).one()
            persisted_fresh = Migration.query.filter_by(
                migration_id="fresh-approved-attempt"
            ).one()
            self.assertEqual(persisted_original.status, "manual_review_required")
            self.assertIsNone(persisted_original.active_identity)
            self.assertEqual(persisted_fresh.status, "preparing")
            self.assertEqual(persisted_fresh.active_identity, "lambda-identity")
            self.assertEqual(persisted_fresh.worker_token, "fresh-worker-token")

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
