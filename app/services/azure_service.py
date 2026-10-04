from azure.identity import ClientSecretCredential

from azure.mgmt.resource.resources import (
    ResourceManagementClient
)

import uuid
from flask import current_app

azure_sessions = {}

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

        credential = ClientSecretCredential(

            tenant_id=tenant_id,

            client_id=client_id,

            client_secret=client_secret

        )

        resource_client = ResourceManagementClient(

            credential,

            subscription_id

        )

        list(

            resource_client.resource_groups.list(

                top=1

            )

        )

        session_id = str(

            uuid.uuid4()

        )

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

def get_azure_session(
    session_id
):

    return azure_sessions.get(session_id)
