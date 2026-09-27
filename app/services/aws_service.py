"""
==========================================================
AI CLOUD MIGRATION
AWS SERVICE
==========================================================

Business Logic Layer

Routes
    ↓
AWS Service
    ↓
AWS Scanner
"""

import uuid
import time
import boto3
from app.scanners.aws_scanner import scan_all_resources
from app.ai.ai_engine import ai_engine
from app.mappers.mapping_engine import mapping_engine
from flask import current_app

from app.security.logging_utils import log_event

from botocore.exceptions import (
    ClientError,
    BotoCoreError
)


# ==========================================================
# TEMPORARY MIGRATION SESSIONS
# ==========================================================

migration_sessions = {}

SESSION_TIMEOUT = 15 * 60

# ==========================================================
# CREATE TEMP SESSION
# ==========================================================

def create_session(
    aws_session,
    account_id,
    region,
    target,
    user_id
):

    session_id = str(uuid.uuid4())

    migration_sessions[session_id] = {

        "aws_session": aws_session,

        "account_id": account_id,

        "region": region,

        "target": target,

        "user_id": user_id,

        "created_at": time.time()

    }

    return session_id

# ==========================================================
# GET SESSION
# ==========================================================

def get_session(session_id):

    migration = migration_sessions.get(
        session_id
    )

    if not migration:

        return None


    age = (
        time.time()
        -
        migration["created_at"]
    )


    if age > SESSION_TIMEOUT:

        migration_sessions.pop(
            session_id,
            None
        )

        return None


    return migration

# ==========================================================
# REMOVE SESSION
# ==========================================================

def remove_session(session_id):

    migration_sessions.pop(
        session_id,
        None
    )

# ==========================================================
# CONNECT AWS
# ==========================================================

def connect_aws(

    access_key,

    secret_key,

    region,

    target,
    user_id

):

    try:

        # ------------------------------------------
        # Create AWS Session
        # ------------------------------------------

        aws_session = boto3.Session(

            aws_access_key_id=access_key,

            aws_secret_access_key=secret_key,

            region_name=region

        )

        # ------------------------------------------
        # Verify Identity
        # ------------------------------------------

        sts = aws_session.client("sts")

        identity = sts.get_caller_identity()

        # ------------------------------------------
        # Create Migration Session
        # ------------------------------------------

        session_id = create_session(

            aws_session,

            identity.get("Account"),

            region,

            target,
            user_id

        )

        return {

            "success": True,

            "session_id": session_id,

            "region": region,

            "target": target,

            "message": "AWS connection verified successfully."

        }

    except ClientError:

        log_event(current_app.logger, "aws_connection_failed", user_id=user_id, operation="connect", category="authentication")

        return {

            "success": False,

            "message":
                "AWS authentication failed. Check your credentials."

        }

    except BotoCoreError:

        log_event(current_app.logger, "aws_connection_failed", user_id=user_id, operation="connect", category="network")

        return {

            "success": False,

            "message":
                "Unable to communicate with AWS."

        }

    except Exception:

        current_app.logger.error("aws_connection_failed user_id=%s operation=connect category=unexpected", user_id)

        return {

            "success": False,

            "message":
                "Unexpected AWS connection error."

        }

# ==========================================================
# SCAN AWS RESOURCES
# ==========================================================

def scan_resources(session_id, target="azure", user_id=None):

    migration = get_session(session_id)

    if not migration:

        return {

            "success": False,

            "message": "Migration session expired."

        }

    if user_id is not None and migration.get("user_id") != user_id:
        return {"success": False, "message": "Migration session is not available."}

    aws_session = migration["aws_session"]

    try:

        resources = scan_all_resources(
            aws_session
        )

        recommendations = ai_engine.analyze_resources(resources,"AWS", migration["target"])

        migration_plan = mapping_engine.generate_plan(

            "AWS",

            migration["target"],

            recommendations

        )

        return {

            "success": True,

            "resources": resources,

            "recommendations": recommendations,

            "migration_plan": migration_plan

        }

    except Exception:
        current_app.logger.error("aws_scan_failed user_id=%s operation=scan category=cloud", user_id)
        return {
            "success": False,
            "message": "AWS resource scanning failed."
        }
