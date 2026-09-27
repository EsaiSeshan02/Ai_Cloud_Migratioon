import unittest

from botocore.exceptions import ClientError

from app import create_app
from app.ai.ai_engine import ai_engine
from app.mappers.cloud_mapper import PLANNING_ONLY, SUPPORTED_EXECUTION
from app.scanners.aws_scanner import scan_all_resources, scan_ec2, scan_lambda, scan_rds, scan_s3


class FakePaginator:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def paginate(self, **kwargs):
        self.calls.append(kwargs)
        return self.pages


class FakeEc2Client:
    def __init__(self):
        self.paginator = FakePaginator([
            {"Reservations": [{"Instances": [{
                "InstanceId": "i-one", "InstanceType": "t3.micro",
                "State": {"Name": "running"}, "Placement": {"AvailabilityZone": "us-east-1a"},
                "ImageId": "ami-example", "Architecture": "x86_64", "PlatformDetails": "Linux/UNIX",
                "RootDeviceName": "/dev/xvda", "RootDeviceType": "ebs", "VpcId": "vpc-1", "SubnetId": "subnet-1",
                "Tags": [{"Key": "Name", "Value": "first"}],
                "SecurityGroups": [{"GroupId": "sg-1", "GroupName": "web"}],
                "BlockDeviceMappings": [{"DeviceName": "/dev/xvda", "Ebs": {"VolumeId": "vol-1", "Encrypted": True, "DeleteOnTermination": True}}],
            }]}]},
            {"Reservations": [{"Instances": [{
                "InstanceId": "i-two", "InstanceType": "t3.small",
                "State": {"Name": "stopped"}, "Placement": {"AvailabilityZone": "us-east-1b"},
            }]}]},
        ])

    def get_paginator(self, name):
        assert name == "describe_instances"
        return self.paginator


class FakeS3Client:
    def list_buckets(self):
        return {"Buckets": [{"Name": "example-bucket", "CreationDate": "2026-01-01"}]}

    def get_bucket_location(self, **_kwargs):
        return {"LocationConstraint": None}

    def get_bucket_versioning(self, **_kwargs):
        return {"Status": "Enabled"}

    def get_bucket_encryption(self, **_kwargs):
        return {"ServerSideEncryptionConfiguration": {"Rules": [{}]}}


class FakeRdsClient:
    def get_paginator(self, name):
        assert name == "describe_db_instances"
        return FakePaginator([{"DBInstances": [{
            "DBInstanceIdentifier": "orders", "Engine": "postgres", "EngineVersion": "16.1",
            "DBInstanceClass": "db.t4g.medium", "DBInstanceStatus": "available",
            "AvailabilityZone": "us-east-1a", "AllocatedStorage": 100, "StorageType": "gp3",
            "StorageEncrypted": True, "MultiAZ": True, "PubliclyAccessible": False,
            "BackupRetentionPeriod": 7, "Endpoint": {"Address": "not-returned.example"},
        }]}])


class FakeLambdaClient:
    def __init__(self):
        self.event_paginator = FakePaginator([{"EventSourceMappings": [{"EventSourceArn": "arn:aws:sqs:region:account:queue"}]}])

    def get_paginator(self, name):
        if name == "list_functions":
            return FakePaginator([{"Functions": [{
                "FunctionName": "process-orders", "Runtime": "python3.12", "Architectures": ["arm64"],
                "MemorySize": 512, "Timeout": 30, "LastModified": "2026-01-01T00:00:00.000+0000",
                "Handler": "app.handler", "VpcConfig": {"VpcId": "vpc-1"}, "Layers": [{"Arn": "not-returned"}],
                "TracingConfig": {"Mode": "Active"}, "Environment": {"Variables": {"SECRET": "not-returned"}},
            }]}])
        if name == "list_event_source_mappings":
            return self.event_paginator
        raise AssertionError(name)


class FakeSession:
    def __init__(self, clients):
        self.clients = clients

    def client(self, name):
        return self.clients[name]


class FailingEc2Client:
    def get_paginator(self, _name):
        raise ClientError({"Error": {"Code": "AccessDenied", "Message": "denied"}}, "DescribeInstances")


class AwsScannerTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-only-secret-key-not-used-in-production",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
        })

    def test_ec2_pagination_and_assessment_metadata(self):
        client = FakeEc2Client()
        with self.app.app_context():
            result = scan_ec2(FakeSession({"ec2": client}))
        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 2)
        first = result["resources"][0]
        self.assertEqual(first["resource_id"], "i-one")
        self.assertEqual(first["image_id"], "ami-example")
        self.assertEqual(first["architecture"], "x86_64")
        self.assertEqual(first["root_volume"]["volume_id"], "vol-1")
        self.assertEqual(first["security_groups"][0]["group_id"], "sg-1")
        self.assertEqual(len(client.paginator.calls), 1)

    def test_s3_metadata_assessment_does_not_list_objects(self):
        with self.app.app_context():
            result = scan_s3(FakeSession({"s3": FakeS3Client()}))
        bucket = result["resources"][0]
        self.assertTrue(result["success"])
        self.assertEqual(bucket["region"], "us-east-1")
        self.assertEqual(bucket["versioning_status"], "Enabled")
        self.assertEqual(bucket["encryption_status"], "Configured")
        self.assertFalse(bucket["object_inventory_scanned"])

    def test_rds_discovery_is_normalized_and_planning_only(self):
        with self.app.app_context():
            result = scan_rds(FakeSession({"rds": FakeRdsClient()}))
        database = result["resources"][0]
        self.assertEqual(database["service"], "RDS")
        self.assertEqual(database["engine"], "postgres")
        self.assertEqual(database["engine_family"], "postgresql")
        self.assertTrue(database["storage_encrypted"])
        recommendation = ai_engine.analyze_resources({"rds": result}, "AWS", "Azure")[0]
        self.assertEqual(recommendation["execution_classification"], PLANNING_ONLY)

    def test_lambda_discovery_omits_environment_values(self):
        client = FakeLambdaClient()
        with self.app.app_context():
            result = scan_lambda(FakeSession({"lambda": client}))
        function = result["resources"][0]
        self.assertEqual(function["service"], "Lambda")
        self.assertEqual(function["architecture"], "arm64")
        self.assertEqual(function["event_source_types"], ["sqs"])
        self.assertFalse(function["environment_variables_included"])
        self.assertNotIn("Environment", function)
        recommendation = ai_engine.analyze_resources({"lambda": result}, "AWS", "Azure")[0]
        self.assertEqual(recommendation["execution_classification"], PLANNING_ONLY)

    def test_provider_failures_are_safe(self):
        with self.app.app_context():
            result = scan_ec2(FakeSession({"ec2": FailingEc2Client()}))
        self.assertFalse(result["success"])
        self.assertEqual(result["resources"], [])
        self.assertNotIn("AccessDenied", result["message"])

    def test_all_services_share_normalized_output_and_mapping_capabilities(self):
        session = FakeSession({
            "ec2": FakeEc2Client(), "s3": FakeS3Client(), "rds": FakeRdsClient(), "lambda": FakeLambdaClient(),
        })
        with self.app.app_context():
            results = scan_all_resources(session)
        self.assertEqual(set(results), {"ec2", "s3", "rds", "lambda"})
        for result in results.values():
            self.assertTrue(result["success"])
            for resource in result["resources"]:
                self.assertTrue({"service", "resource_type", "resource_id", "name"}.issubset(resource))
        recommendations = ai_engine.analyze_resources(results, "AWS", "Azure")
        classifications = {item["source_service"]: item["execution_classification"] for item in recommendations}
        self.assertEqual(classifications["S3"], SUPPORTED_EXECUTION)
        self.assertEqual(classifications["EC2"], PLANNING_ONLY)
        self.assertEqual(classifications["RDS"], PLANNING_ONLY)
        self.assertEqual(classifications["Lambda"], PLANNING_ONLY)


if __name__ == "__main__":
    unittest.main()
