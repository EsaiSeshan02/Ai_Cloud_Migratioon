from azure.identity import ClientSecretCredential

from azure.mgmt.resource.resources import (
    ResourceManagementClient
)

import uuid
from flask import current_app


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
    role="target",
    user_id=None
):

    if role != "target":
        return {"success": False, "message": "Azure sessions are available only as AWS migration targets."}

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

    return azure_sessions.get(session_id)
