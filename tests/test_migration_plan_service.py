import json
import re
import time
import unittest
from unittest.mock import patch

from app import create_app
from app.extensions import bcrypt, db
from app.models.migration import MigrationPlan, MigrationPlanResource
from app.models.user import User
from app.mappers.mapping_engine import MappingEngine
from app.services.aws_service import migration_sessions
from app.services.azure_service import azure_sessions
from app.services.migration_plan_service import (
    generate_migration_plan,
    get_user_plan,
    serialize_plan,
)


def normalized_resources():
    return {
        "s3": {"success": True, "resources": [{
            "service": "S3", "resource_type": "aws_s3_bucket", "resource_id": "bucket", "name": "bucket",
            "bucket_name": "bucket", "region": "eastus", "versioning_status": "Enabled",
            "encryption_status": "Configured", "object_inventory_scanned": False,
        }]},
        "ec2": {"success": True, "resources": [{
            "service": "EC2", "resource_type": "aws_ec2_instance", "resource_id": "i-1", "name": "server",
            "image_id": "ami-1", "architecture": "x86_64", "platform": "Linux/UNIX",
            "root_volume": {"volume_id": "vol-1"}, "vpc_id": "vpc-1", "subnet_id": "subnet-1", "security_groups": [{"group_id": "sg-1"}],
        }]},
        "rds": {"success": True, "resources": [
            {"service": "RDS", "resource_type": "aws_rds_instance", "resource_id": "pg", "name": "pg", "engine": "postgres", "engine_version": "16"},
            {"service": "RDS", "resource_type": "aws_rds_instance", "resource_id": "unknown", "name": "unknown", "engine": "oracle"},
        ]},
        "lambda": {"success": True, "resources": [{
            "service": "Lambda", "resource_type": "aws_lambda_function", "resource_id": "fn", "name": "fn",
            "runtime": "python3.12", "architecture": "arm64", "handler": "app.handler", "vpc_enabled": True,
            "event_source_types": ["sqs"], "environment_variables_included": False,
            "Environment": {"Variables": {"PASSWORD": "must-not-persist"}}, "secret": "must-not-persist",
        }]},
    }


def azure_normalized_resources():
    return {
        "vm": {"success": True, "resources": [{
            "service": "Azure Virtual Machine", "resource_type": "virtual_machine", "resource_id": "vm-1", "name": "vm-1",
            "vm_size": "Standard_D2s_v5", "os_type": "Linux", "data_disk_count": 1, "location": "eastus",
        }]},
        "storage": {"success": True, "resources": [{
            "service": "Azure Storage Account", "resource_type": "storage_account", "resource_id": "store-1", "name": "store-1",
            "kind": "StorageV2", "sku": "Standard_LRS", "location": "eastus",
        }]},
        "sql": {"success": True, "resources": [{
            "service": "Azure SQL Database", "resource_type": "sql_database", "resource_id": "sql-1", "name": "orders",
            "server_name": "server-1", "sku_tier": "GeneralPurpose", "connection_string": "must-not-persist",
        }]},
    }


class MigrationPlanServiceTests(unittest.TestCase):
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
            self.owner = User(name="Owner", email="owner-plan@example.com", password_hash=bcrypt.generate_password_hash("secure-password-123").decode())
            self.other = User(name="Other", email="other-plan@example.com", password_hash=bcrypt.generate_password_hash("secure-password-123").decode())
            db.session.add_all([self.owner, self.other])
            db.session.commit()
            self.owner_id, self.other_id = self.owner.id, self.other.id

    def tearDown(self):
        migration_sessions.clear()
        azure_sessions.clear()
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def _plan(self, user_id=None, resources=None):
        return generate_migration_plan(
            user_id=user_id or self.owner_id, source_cloud="aws", target_cloud="azure",
            source_session_reference="source-session", target_session_reference="target-session",
            normalized_resources=resources if resources is not None else normalized_resources(),
        )

    def _csrf(self):
        response = self.client.get("/")
        return re.search(r'name="csrf-token" content="([^"]+)"', response.get_data(as_text=True)).group(1)

    def _login_owner(self):
        self.client.post("/login", data={
            "csrf_token": self._csrf(), "email": "owner-plan@example.com", "password": "secure-password-123",
        })

    def test_plan_and_resources_persist_with_stable_identifier(self):
        with self.app.app_context():
            plan = self._plan()
            stored = MigrationPlan.query.filter_by(plan_id=plan.plan_id).one()
            self.assertEqual(stored.user_id, self.owner_id)
            self.assertEqual(stored.resource_count, 5)
            self.assertEqual(stored.execution_ready_count, 1)
            self.assertEqual(stored.planning_review_count, 4)
            self.assertEqual(MigrationPlanResource.query.filter_by(plan_id=stored.id).count(), 5)

    def test_capabilities_and_preflight_findings_are_preserved(self):
        with self.app.app_context():
            plan = self._plan()
            resources = {item.service + ":" + item.resource_id: item for item in plan.resources}
            self.assertEqual(resources["S3:bucket"].capability_classification, "supported_execution")
            self.assertEqual(resources["EC2:i-1"].capability_classification, "planning_only")
            self.assertEqual(resources["RDS:pg"].capability_classification, "planning_only")
            self.assertEqual(resources["RDS:unknown"].capability_classification, "manual_review")
            self.assertEqual(resources["Lambda:fn"].capability_classification, "planning_only")
            self.assertTrue(json.loads(resources["EC2:i-1"].preflight_findings))
            self.assertTrue(json.loads(resources["RDS:unknown"].manual_review_reasons))

    def test_secrets_are_not_persisted_or_serialized(self):
        with self.app.app_context():
            plan = self._plan()
            serialized = json.dumps(serialize_plan(plan))
            stored_metadata = MigrationPlanResource.query.filter_by(service="Lambda").one().source_metadata
            self.assertNotIn("must-not-persist", stored_metadata)
            self.assertNotIn("Environment", stored_metadata)
            self.assertNotIn("must-not-persist", serialized)

    def test_empty_and_invalid_resources_are_handled_safely(self):
        with self.app.app_context():
            empty = self._plan(resources={})
            self.assertEqual(empty.status, "empty")
            self.assertEqual(empty.resource_count, 0)
            with self.assertRaises(ValueError):
                self._plan(resources={"bad": {"success": True, "resources": "not-a-list"}})

    def test_plan_lookup_is_owner_scoped_in_service_layer(self):
        with self.app.app_context():
            plan = self._plan()
            self.assertIsNotNone(get_user_plan(plan.plan_id, self.owner_id))
            self.assertIsNone(get_user_plan(plan.plan_id, self.other_id))

    def test_plan_resources_inherit_owner_scope_from_their_plan(self):
        with self.app.app_context():
            plan = self._plan()
            resource = MigrationPlanResource.query.filter_by(plan_id=plan.id).first()
            self.assertEqual(resource.plan.user_id, self.owner_id)
            self.assertIsNone(get_user_plan(resource.plan.plan_id, self.other_id))

    def test_ec2_preflight_is_deterministic_and_preserves_safe_dependencies(self):
        with self.app.app_context():
            plan = self._plan()
            ec2 = next(item for item in plan.resources if item.service == "EC2")
            findings = {item["code"] for item in json.loads(ec2.preflight_findings)}
            dependencies = json.loads(ec2.dependencies)
            self.assertEqual(ec2.capability_classification, "planning_only")
            self.assertEqual(ec2.risk_level, "high")
            self.assertIn("image_conversion_required", findings)
            self.assertIn("cutover_rollback_required", findings)
            self.assertIn("VPC mapping", dependencies)
            self.assertIn("Security-group to NSG mapping", dependencies)
            self.assertNotIn("vpc-1", json.dumps(dependencies))

    def test_rds_engine_assessment_keeps_engine_specific_target_and_manual_risk(self):
        with self.app.app_context():
            plan = self._plan()
            resources = {item.resource_id: item for item in plan.resources if item.service == "RDS"}
            self.assertEqual(resources["pg"].target_service, "Azure Database for PostgreSQL")
            self.assertEqual(resources["pg"].capability_classification, "planning_only")
            self.assertEqual(resources["pg"].risk_level, "high")
            self.assertEqual(resources["unknown"].capability_classification, "manual_review")
            self.assertEqual(resources["unknown"].risk_level, "manual_review")

    def test_lambda_assessment_preserves_dependency_and_secret_boundaries(self):
        with self.app.app_context():
            plan = self._plan()
            function = next(item for item in plan.resources if item.service == "Lambda")
            findings = {item["code"] for item in json.loads(function.preflight_findings)}
            dependencies = json.loads(function.dependencies)
            self.assertEqual(function.capability_classification, "planning_only")
            self.assertIn("VPC/network design", dependencies)
            self.assertIn("Event-source trigger conversion", dependencies)
            self.assertIn("environment_secret_handling", findings)
            self.assertNotIn("must-not-persist", function.source_metadata)

    def test_s3_remains_supported_with_explainable_risk(self):
        with self.app.app_context():
            plan = self._plan()
            bucket = next(item for item in plan.resources if item.service == "S3")
            findings = {item["code"] for item in json.loads(bucket.preflight_findings)}
            self.assertEqual(bucket.capability_classification, "supported_execution")
            self.assertEqual(bucket.risk_level, "low")
            self.assertIn("bucket_policy_lifecycle_review", findings)
            self.assertIn("object_inventory_deferred", findings)

    def test_azure_plan_assessments_never_become_executable(self):
        with self.app.app_context():
            plan = generate_migration_plan(
                user_id=self.owner_id, source_cloud="azure", target_cloud="aws",
                source_session_reference="azure-source", target_session_reference="aws-target",
                normalized_resources=azure_normalized_resources(),
            )
            resources = {item.service: item for item in plan.resources}
            self.assertEqual(resources["Azure Virtual Machine"].capability_classification, "planning_only")
            self.assertEqual(resources["Azure Virtual Machine"].risk_level, "high")
            self.assertEqual(resources["Azure Storage Account"].capability_classification, "planning_only")
            self.assertEqual(resources["Azure Storage Account"].risk_level, "medium")
            self.assertEqual(resources["Azure SQL Database"].capability_classification, "manual_review")
            self.assertEqual(resources["Azure SQL Database"].risk_level, "manual_review")
            self.assertNotIn("must-not-persist", resources["Azure SQL Database"].source_metadata)

    def test_plan_serialization_exposes_assessment_not_sensitive_metadata(self):
        with self.app.app_context():
            plan = self._plan()
            payload = serialize_plan(plan)
            resource = next(item for item in payload["resources"] if item["service"] == "EC2")
            self.assertTrue({"risk_level", "dependencies", "preflight_findings", "manual_review_reasons", "recommendation"}.issubset(resource))
            self.assertEqual(resource["recommendation"]["risk_level"], resource["risk_level"])
            self.assertNotIn("source_metadata", resource)
            self.assertNotIn("must-not-persist", json.dumps(payload))

    def test_fixed_duration_estimate_is_not_emitted(self):
        plan = MappingEngine().generate_plan("AWS", "Azure", [])
        self.assertNotIn("estimated_time", plan)
        self.assertEqual(plan["estimated_duration"], "requires_assessment")

    def test_plan_api_create_list_get_and_ownership(self):
        self._login_owner()
        migration_sessions["owner-source"] = {"user_id": self.owner_id, "created_at": time.time(), "aws_session": object(), "target": "azure"}
        azure_sessions["owner-target"] = {"user_id": self.owner_id, "role": "target"}
        scan_result = {"success": True, "resources": normalized_resources()}
        with patch("app.services.aws_service.scan_resources", return_value=scan_result):
            response = self.client.post("/api/migration-plans", json={
                "source_session_id": "owner-source", "target_session_id": "owner-target",
                "source_cloud": "aws", "target_cloud": "azure",
            }, headers={"X-CSRFToken": self._csrf()})
        self.assertEqual(response.status_code, 201)
        plan_id = response.get_json()["plan"]["plan_id"]
        self.assertEqual(self.client.get("/api/migration-plans").get_json()["plans"][0]["plan_id"], plan_id)
        self.assertEqual(self.client.get(f"/api/migration-plans/{plan_id}").status_code, 200)

        with self.app.app_context():
            foreign = self._plan(user_id=self.other_id)
            foreign_plan_id = foreign.plan_id
        self.assertEqual(self.client.get(f"/api/migration-plans/{foreign_plan_id}").status_code, 403)


if __name__ == "__main__":
    unittest.main()
