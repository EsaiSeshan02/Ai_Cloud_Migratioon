import unittest

from app.ai.ai_engine import ai_engine
from app.mappers.cloud_mapper import (
    MANUAL_REVIEW,
    PLANNING_ONLY,
    SUPPORTED_EXECUTION,
    get_cloud_mapping,
)
from app.mappers.mapping_engine import mapping_engine
from app.services.cloud_mapping import get_service_mapping


class PhaseThreeMappingTests(unittest.TestCase):
    def test_aws_azure_mapping_lookup_uses_authoritative_metadata(self):
        mapping = get_cloud_mapping("aws", "azure", "S3")
        self.assertEqual(mapping["target_service"], "Azure Blob Storage")
        self.assertEqual(mapping["execution_classification"], SUPPORTED_EXECUTION)
        # Historical imports are a facade, not a competing mapping table.
        self.assertEqual(get_service_mapping("aws", "azure", "S3"), mapping)

    def test_s3_is_the_only_current_supported_execution_mapping(self):
        mapping = get_cloud_mapping("AWS", "Azure", "S3")
        self.assertEqual(mapping["execution_classification"], SUPPORTED_EXECUTION)
        self.assertIn("supported", mapping["status"].lower())

    def test_ec2_cannot_report_ready_for_execution(self):
        mapping = get_cloud_mapping("AWS", "Azure", "EC2")
        self.assertEqual(mapping["target_service"], "Azure Virtual Machine")
        self.assertEqual(mapping["execution_classification"], PLANNING_ONLY)
        self.assertNotIn("ready", mapping["status"].lower())

    def test_rds_requires_engine_assessment_and_never_reports_execution_ready(self):
        unknown = get_cloud_mapping("AWS", "Azure", "RDS")
        postgres = get_cloud_mapping("AWS", "Azure", "RDS", {"engine": "postgres"})
        self.assertEqual(unknown["execution_classification"], MANUAL_REVIEW)
        self.assertEqual(postgres["target_service"], "Azure Database for PostgreSQL")
        self.assertEqual(postgres["execution_classification"], PLANNING_ONLY)
        self.assertNotIn("ready", postgres["status"].lower())

    def test_lambda_is_planning_only(self):
        mapping = get_cloud_mapping("AWS", "Azure", "Lambda")
        self.assertEqual(mapping["target_service"], "Azure Functions")
        self.assertEqual(mapping["execution_classification"], PLANNING_ONLY)
        self.assertNotIn("ready", mapping["status"].lower())

    def test_recommendations_and_plans_preserve_capability_classification(self):
        resources = {
            "services": {
                "success": True,
                "resources": [
                    {"service": "EC2", "name": "vm", "type": "t3.micro"},
                    {"service": "S3", "name": "bucket", "bucket_name": "bucket"},
                    {"service": "Lambda", "name": "function"},
                ],
            }
        }
        recommendations = ai_engine.analyze_resources(resources, "AWS", "Azure")
        classifications = {item["source_service"]: item["execution_classification"] for item in recommendations}
        self.assertEqual(classifications["EC2"], PLANNING_ONLY)
        self.assertEqual(classifications["S3"], SUPPORTED_EXECUTION)
        self.assertEqual(classifications["Lambda"], PLANNING_ONLY)
        plan = mapping_engine.generate_plan("AWS", "Azure", recommendations)
        planned = {item["source"]: item["execution_classification"] for item in plan["resources"]}
        self.assertEqual(planned, classifications)


if __name__ == "__main__":
    unittest.main()
