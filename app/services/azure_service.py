from azure.identity import ClientSecretCredential

from azure.mgmt.resource.resources import (
    ResourceManagementClient
)

from azure.mgmt.compute import (
    ComputeManagementClient
)

from azure.mgmt.storage import (
    StorageManagementClient
)

from azure.mgmt.sql import (
    SqlManagementClient
)

import uuid
from flask import current_app

from app.security.logging_utils import log_event
from app.scanners.azure_scanner import scan_all_resources
from app.ai.ai_engine import AIEngine
from app.mappers.mapping_engine import MappingEngine


# ==========================================================
# AZURE MIGRATION SESSIONS
# ==========================================================

azure_sessions = {}


# ==========================================================
# CONNECT AZURE
# ==========================================================

def connect_azure(
    tenant_id,
    client_id,
    client_secret,
    subscription_id,
    connected_cloud=None,
    role="source",
    user_id=None
):

    try:

        # --------------------------------------------------
        # CREATE CREDENTIAL
        # --------------------------------------------------

        credential = ClientSecretCredential(

            tenant_id=tenant_id,

            client_id=client_id,

            client_secret=client_secret

        )


        # --------------------------------------------------
        # RESOURCE MANAGEMENT CLIENT
        # --------------------------------------------------

        resource_client = ResourceManagementClient(

            credential,

            subscription_id

        )


        # --------------------------------------------------
        # TEST CONNECTION
        # --------------------------------------------------
        #
        # This verifies that:
        #
        # 1. Credentials are valid
        # 2. Azure authentication succeeds
        # 3. Subscription can be accessed
        #
        # --------------------------------------------------

        list(

            resource_client.resource_groups.list(

                top=1

            )

        )


        # --------------------------------------------------
        # CREATE SESSION ID
        # --------------------------------------------------

        session_id = str(

            uuid.uuid4()

        )


        # --------------------------------------------------
        # SAVE SESSION
        # --------------------------------------------------

        azure_sessions[session_id] = {

            # Azure connection details

            "credential":
                credential,

            "subscription_id":
                subscription_id,

            "resource_client":
                resource_client,


            # Cloud information

            "cloud":
                "azure",

            "role":
                role,

            "connected_cloud":
                connected_cloud,

            "user_id": user_id

        }


        # --------------------------------------------------
        # SUCCESS RESPONSE
        # --------------------------------------------------

        return {

            "success":
                True,

            "message":
                "Azure connected successfully.",

            "session_id":
                session_id,

            "cloud":
                "azure",

            "role":
                role,

            "connected_cloud":
                connected_cloud

        }


    except Exception:

        current_app.logger.error("azure_connection_failed user_id=%s operation=connect category=cloud", user_id)


        return {

            "success":
                False,

            "message":
                "Azure authentication or connection failed."

        }


# ==========================================================
# GET AZURE SESSION
# ==========================================================

def get_azure_session(
    session_id
):

    return azure_sessions.get(

        session_id

    )


# ==========================================================
# SCAN AZURE RESOURCES
# ==========================================================

def scan_azure_resources(session_id, user_id=None):
    migration = get_azure_session(session_id)
    if not migration:
        return {"success": False, "message": "Azure migration session expired."}
    if user_id is not None and migration.get("user_id") != user_id:
        return {"success": False, "message": "Migration session is not available."}
    if migration.get("role") != "source":
        return {"success": False, "message": "This Azure session is configured as a target cloud and cannot be scanned as a source."}

    try:
        credential = migration["credential"]
        subscription_id = migration["subscription_id"]
        log_event(current_app.logger, "azure_scan_started", user_id=user_id, operation="scan", status="running")
        resources = scan_all_resources(
            ComputeManagementClient(credential, subscription_id),
            StorageManagementClient(credential, subscription_id),
            SqlManagementClient(credential, subscription_id),
        )
        target_cloud = migration.get("connected_cloud")
        successful = [result for result in resources.values() if result.get("success")]
        ai_engine = AIEngine()
        mapping_engine = MappingEngine()
        recommendations = ai_engine.analyze_resources(resources, "Azure", target_cloud)
        migration_plan = mapping_engine.generate_plan("Azure", target_cloud, recommendations)
        scan_result = {
            "success": bool(successful), "source_cloud": "azure", "target_cloud": target_cloud,
            "resources": resources, "recommendations": recommendations, "migration_plan": migration_plan,
            # Legacy, non-secret result arrays retained for existing consumers.
            "virtual_machines": resources["azure_virtual_machines"]["resources"],
            "storage_accounts": resources["azure_storage_accounts"]["resources"],
            "sql_databases": resources["azure_sql_databases"]["resources"],
            "summary": {
                "virtual_machines": len(resources["azure_virtual_machines"]["resources"]),
                "storage_accounts": len(resources["azure_storage_accounts"]["resources"]),
                "sql_databases": len(resources["azure_sql_databases"]["resources"]),
            },
        }
        if not successful:
            scan_result["message"] = "Azure resource discovery was unavailable."
        migration["scan_result"] = scan_result
        return scan_result
    except Exception:
        current_app.logger.error("azure_scan_failed user_id=%s operation=scan category=cloud", user_id)
        return {"success": False, "message": "Azure resource scanning failed."}
