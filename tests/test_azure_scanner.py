import unittest
from pathlib import Path
from types import SimpleNamespace

from app import create_app
from app.ai.ai_engine import ai_engine
from app.mappers.cloud_mapper import PLANNING_ONLY, SUPPORTED_EXECUTION
from app.scanners.azure_scanner import (
    scan_all_resources,
    scan_sql_databases,
    scan_storage_accounts,
    scan_virtual_machines,
)


ARM_PREFIX = "/subscriptions/sub/resourceGroups/rg-one/providers/"


class FakeComputeClient:
    virtual_machines = None

    def __init__(self):
        vm = SimpleNamespace(
            id=ARM_PREFIX + "Microsoft.Compute/virtualMachines/vm-one",
            name="vm-one", location="eastus", zones=["1"],
            hardware_profile=SimpleNamespace(vm_size="Standard_D2s_v5"),
            storage_profile=SimpleNamespace(
                os_disk=SimpleNamespace(os_type="Linux"), data_disks=[SimpleNamespace()]
            ),
            properties=SimpleNamespace(provisioning_state="Succeeded"),
            secret_value="not-returned",
        )
        self.virtual_machines = SimpleNamespace(list_all=lambda: [vm])


class FakeStorageClient:
    storage_accounts = None

    def __init__(self):
        account = SimpleNamespace(
            id=ARM_PREFIX + "Microsoft.Storage/storageAccounts/storeone",
            name="storeone", location="eastus", kind="StorageV2",
            sku=SimpleNamespace(name="Standard_LRS"), access_tier="Hot",
            enable_https_traffic_only=True, public_network_access="Enabled",
            allow_blob_public_access=False, encryption=SimpleNamespace(),
            primary_key="must-not-return", connection_string="must-not-return",
        )
        self.storage_accounts = SimpleNamespace(list=lambda: [account])


class FakeSqlClient:
    databases = None

    def __init__(self):
        database = SimpleNamespace(
            id=ARM_PREFIX + "Microsoft.Sql/servers/server-one/databases/orders",
            name="orders", location="eastus", status="Online",
            sku=SimpleNamespace(name="GP_Gen5_2", tier="GeneralPurpose"),
            max_size_bytes=1073741824, collation="SQL_Latin1_General_CP1_CI_AS",
            administrator_login_password="must-not-return",
        )
        self.databases = SimpleNamespace(list_by_subscription=lambda: [database])


class FailingStorageClient:
    storage_accounts = SimpleNamespace(list=lambda: (_ for _ in ()).throw(RuntimeError("credential-value")))


class AzureScannerTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-only-secret-key-not-used-in-production",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
        })

    def test_vm_discovery_is_normalized_and_secret_free(self):
        with self.app.app_context():
            result = scan_virtual_machines(FakeComputeClient())
        vm = result["resources"][0]
        self.assertTrue(result["success"])
        self.assertEqual(vm["service"], "Azure Virtual Machine")
        self.assertEqual(vm["resource_type"], "virtual_machine")
        self.assertEqual(vm["resource_group"], "rg-one")
        self.assertEqual(vm["os_type"], "Linux")
        self.assertNotIn("secret_value", vm)

    def test_storage_discovery_is_normalized_and_never_returns_keys(self):
        with self.app.app_context():
            result = scan_storage_accounts(FakeStorageClient())
        account = result["resources"][0]
        self.assertTrue(result["success"])
        self.assertEqual(account["service"], "Azure Storage Account")
        self.assertEqual(account["resource_type"], "storage_account")
        self.assertTrue(account["https_only"])
        self.assertNotIn("primary_key", account)
        self.assertNotIn("connection_string", account)

    def test_sql_discovery_is_normalized_and_never_returns_credentials(self):
        with self.app.app_context():
            result = scan_sql_databases(FakeSqlClient())
        database = result["resources"][0]
        self.assertTrue(result["success"])
        self.assertEqual(database["service"], "Azure SQL Database")
        self.assertEqual(database["resource_type"], "sql_database")
        self.assertEqual(database["sku_tier"], "GeneralPurpose")
        self.assertNotIn("administrator_login_password", database)

    def test_provider_failure_is_isolated_and_safe(self):
        with self.app.app_context():
            result = scan_all_resources(FakeComputeClient(), FailingStorageClient(), FakeSqlClient())
        self.assertTrue(result["azure_virtual_machines"]["success"])
        self.assertFalse(result["azure_storage_accounts"]["success"])
        self.assertTrue(result["azure_sql_databases"]["success"])
        self.assertNotIn("credential-value", result["azure_storage_accounts"]["message"])

    def test_azure_discovery_remains_planning_or_manual_review(self):
        with self.app.app_context():
            results = scan_all_resources(FakeComputeClient(), FakeStorageClient(), FakeSqlClient())
        for service_result in results.values():
            for resource in service_result["resources"]:
                self.assertTrue({"service", "resource_type", "resource_id", "name"}.issubset(resource))
        recommendations = ai_engine.analyze_resources(results, "Azure", "AWS")
        classifications = {item["source_service"]: item["execution_classification"] for item in recommendations}
        self.assertEqual(classifications["Azure Virtual Machine"], PLANNING_ONLY)
        self.assertEqual(classifications["Azure Storage Account"], PLANNING_ONLY)
        self.assertNotEqual(classifications["Azure SQL Database"], SUPPORTED_EXECUTION)

    def test_dashboard_has_source_aware_scan_request(self):
        script = Path("app/static/js/migration-dashboard.js").read_text(encoding="utf-8")
        self.assertIn("function getSourceScanRequest", script)
        self.assertIn("function getDashboardCloudContext", script)
        self.assertIn('endpoint: "/api/azure/scan"', script)
        self.assertIn('endpoint: "/api/aws/scan"', script)


if __name__ == "__main__":
    unittest.main()
