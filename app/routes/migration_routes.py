from flask import (
    Blueprint,
    render_template,
    request,
    jsonify,
    abort,
    redirect,
    url_for,
    current_app
)
from flask_login import current_user

from app.models.migration import Migration, MigrationFile, MigrationPlan
from app.security.audit_logger import audit_event


# ==========================================================
# AWS SERVICES
# ==========================================================

from app.services.aws_service import (
    connect_aws,
    get_session
)


# ==========================================================
# AZURE SERVICES
# ==========================================================

from app.services.azure_service import (
    connect_azure,
    get_azure_session
)


# ==========================================================
# S3 MIGRATION SERVICE
# ==========================================================

from app.services.s3_migration_service import migration_progress, resume_s3_migration
from app.services.migration_plan_service import (
    generate_migration_plan,
    list_user_plans,
    serialize_plan,
    approve_lambda_execution_target,
)
from app.services.report_service import generate_report, serialize_report
from app.utils.validators import safe_migration_configuration, valid_s3_bucket_name


# ==========================================================
# MIGRATION BLUEPRINT
# ==========================================================

migration_bp = Blueprint(
    "migration",
    __name__
)


@migration_bp.before_request
def require_authenticated_user():
    """All cloud credentials, sessions, and migration actions are private."""
    if current_user.is_authenticated:
        return None
    if request.path.startswith("/api/"):
        return jsonify(success=False, message="Please sign in to continue."), 401
    return redirect(url_for("auth.login", next=request.url))


def owned_aws_session(session_id):
    cloud_session = get_session(session_id)
    if not cloud_session:
        abort(401)
    if cloud_session.get("user_id") != current_user.id:
        abort(403)
    return cloud_session


def owned_azure_session(session_id):
    cloud_session = get_azure_session(session_id)
    if not cloud_session:
        abort(401)
    if cloud_session.get("user_id") != current_user.id:
        abort(403)
    return cloud_session


def public_migration_result(result):
    """Return operational status without cloud inventory identifiers or object keys."""
    return {
        key: result[key]
        for key in (
            "success", "message", "status", "migration_id", "total_files",
            "uploaded_files", "failed_files", "total_size_bytes", "total_batches",
            "transferred_bytes", "verified_files", "skipped_files", "manual_review_files",
            "pending_files", "transferring_files", "processed_files", "completed_batches",
            "current_batch", "retry_attempts", "retriable_files", "logical_batch_size_bytes",
        )
        if key in result
    }


def owned_migration_plan(plan_id):
    plan = MigrationPlan.query.filter_by(plan_id=plan_id).first()
    if not plan:
        abort(404)
    if plan.user_id != current_user.id:
        abort(403)
    return plan


# ==========================================================
# SUPPORTED CLOUDS
# ==========================================================

AWS_SOURCE = "aws"
AZURE_TARGET = "azure"


# ==========================================================
# AWS SOURCE PAGE
# ==========================================================

@migration_bp.route("/migration/aws-source")
def aws_source():

    target = request.args.get(
        "target",
        "azure"
    ).strip().lower()


    if target != AZURE_TARGET:
        return "This assistant supports AWS source to Azure target only.", 400


    return render_template(

        "migration/aws-source.html",

        target=target

    )


# ==========================================================
# COMMON CONNECT CLOUD PAGE
# ==========================================================

@migration_bp.route("/migration/connect-cloud")
def connect_cloud():

    source = request.args.get(
        "source",
        ""
    ).strip().lower()

    target = request.args.get(
        "target",
        ""
    ).strip().lower()

    # New parameter used by the source pages
    source_session_id = request.args.get(
        "source_session_id",
        ""
    ).strip()

    # Support older links that still use session_id
    if not source_session_id:

        source_session_id = request.args.get(
            "session_id",
            ""
        ).strip()


    if (source, target) != (AWS_SOURCE, AZURE_TARGET):
        return "This assistant supports AWS source to Azure target only.", 400


    # ------------------------------------------------------
    # VALIDATE SOURCE SESSION
    # ------------------------------------------------------

    if not source_session_id:

        return (
            "Source cloud session is missing.",
            400
        )


    owned_aws_session(source_session_id)


    # ------------------------------------------------------
    # RENDER CONNECT PAGE
    # ------------------------------------------------------

    return render_template(

        "migration/connect-cloud.html",

        source=source,

        target=target,

        source_session_id=source_session_id

    )


# ==========================================================
# MIGRATION DASHBOARD
# ==========================================================

@migration_bp.route("/migration/dashboard")
def migration_dashboard():

    source = request.args.get(
        "source",
        ""
    ).strip().lower()

    target = request.args.get(
        "target",
        ""
    ).strip().lower()

    source_session_id = request.args.get(
        "source_session_id",
        ""
    ).strip()

    target_session_id = request.args.get(
        "target_session_id",
        ""
    ).strip()


    if (source, target) != (AWS_SOURCE, AZURE_TARGET):
        return "This assistant supports AWS source to Azure target only.", 400


    # ------------------------------------------------------
    # VALIDATE SOURCE SESSION
    # ------------------------------------------------------

    if not source_session_id:

        return (
            "Source cloud session is missing.",
            400
        )


    # ------------------------------------------------------
    # VALIDATE TARGET SESSION
    # ------------------------------------------------------

    if not target_session_id:

        return (
            "Target cloud session is missing.",
            400
        )


    owned_aws_session(source_session_id)
    owned_azure_session(target_session_id)


    # ------------------------------------------------------
    # RENDER MIGRATION DASHBOARD
    # ------------------------------------------------------

    return render_template(

        "migration/dashboard-migration.html",

        source=source,

        target=target,

        source_session_id=source_session_id,

        target_session_id=target_session_id

    )

# ==========================================================
# MIGRATION CONFIGURATION PAGE
# ==========================================================

@migration_bp.route("/migration/configure")
def configure_migration():

    source = request.args.get(
        "source",
        ""
    ).strip().lower()

    target = request.args.get(
        "target",
        ""
    ).strip().lower()

    source_session_id = request.args.get(
        "source_session_id",
        ""
    ).strip()

    target_session_id = request.args.get(
        "target_session_id",
        ""
    ).strip()

    if not source_session_id:
        return "Source cloud session is missing.", 400

    if not target_session_id:
        return "Target cloud session is missing.", 400

    if (source, target) != (AWS_SOURCE, AZURE_TARGET):
        abort(400)

    owned_aws_session(source_session_id)
    owned_azure_session(target_session_id)

    return render_template(
        "migration/configure-migration.html",
        source=source,
        target=target,
        source_session_id=source_session_id,
        target_session_id=target_session_id
    )


# ==========================================================
# AWS CONNECT API
# ==========================================================

@migration_bp.route(
    "/api/aws/connect",
    methods=["POST"]
)
def aws_connect():

    data = request.get_json(
        silent=True
    ) or {}


    access_key = data.get(
        "access_key",
        ""
    ).strip()


    secret_key = data.get(
        "secret_key",
        ""
    ).strip()


    region = data.get(
        "region",
        ""
    ).strip()


    target = data.get(
        "target",
        ""
    ).strip().lower()


    # ------------------------------------------------------
    # VALIDATION
    # ------------------------------------------------------

    if not all([
        access_key,
        secret_key,
        region,
        target
    ]):

        return jsonify({

            "success": False,

            "message":
                "All AWS connection fields are required."

        }), 400


    # ------------------------------------------------------
    # VALIDATE TARGET
    # ------------------------------------------------------

    if target != AZURE_TARGET:
        return jsonify(success=False, message="This assistant supports AWS source to Azure target only."), 400


    # ------------------------------------------------------
    # CONNECT AWS
    # ------------------------------------------------------

    result = connect_aws(

        access_key,

        secret_key,

        region,

        target,
        current_user.id

    )


    # ------------------------------------------------------
    # RETURN RESULT
    # ------------------------------------------------------

    if result.get("success"):

        audit_event("aws_connection_verified", user_id=current_user.id, status="success", category="cloud")

        return jsonify(
            result
        )


    return jsonify(
        result
    ), 401


# ==========================================================
# AZURE TARGET VALIDATION API
# ==========================================================
#
# This endpoint is used by connect-cloud.js.
#
# ==========================================================

@migration_bp.route(
    "/api/migration/target/validate",
    methods=["POST"]
)
def validate_target_cloud():

    data = request.get_json(
        silent=True
    ) or {}


    source = data.get(
        "source",
        ""
    ).strip().lower()


    target = data.get(
        "target",
        ""
    ).strip().lower()


    source_session_id = data.get(
        "source_session_id",
        ""
    ).strip()


    if (source, target) != (AWS_SOURCE, AZURE_TARGET):
        return jsonify(success=False, message="This assistant supports AWS source to Azure target only."), 400


    # ------------------------------------------------------
    # VALIDATE SOURCE SESSION
    # ------------------------------------------------------

    if not source_session_id:

        return jsonify({

            "success": False,

            "message":
                "Source session is missing."

        }), 400


    owned_aws_session(source_session_id)


    # ======================================================
    # AZURE TARGET VALIDATION
    # ======================================================

    if target == "azure":

        tenant_id = data.get(
            "tenant_id",
            ""
        ).strip()


        client_id = data.get(
            "client_id",
            ""
        ).strip()


        client_secret = data.get(
            "client_secret",
            ""
        ).strip()


        subscription_id = data.get(
            "subscription_id",
            ""
        ).strip()


        if not all([

            tenant_id,

            client_id,

            client_secret,

            subscription_id

        ]):

            return jsonify({

                "success": False,

                "message":
                    "All Azure credentials are required."

            }), 400


        # --------------------------------------------------
        # CONNECT TARGET AZURE
        # --------------------------------------------------

        result = connect_azure(

            tenant_id=tenant_id,

            client_id=client_id,

            client_secret=client_secret,

            subscription_id=subscription_id,

            connected_cloud=AWS_SOURCE,

            role="target",
            user_id=current_user.id

        )


        if not result.get("success"):

            return jsonify(
                result
            ), 401

        audit_event("azure_target_verified", user_id=current_user.id, status="success", category="cloud")


        # --------------------------------------------------
        # RETURN TARGET SESSION
        # --------------------------------------------------

        return jsonify({

            "success": True,

            "message":
                "Azure target cloud validated successfully.",

            "target_session_id":
                result.get("session_id")

        })

# ==========================================================
# SCAN AWS RESOURCES
# ==========================================================

@migration_bp.route(
    "/api/aws/scan",
    methods=["POST"]
)
def aws_scan():

    data = request.get_json(
        silent=True
    ) or {}

    session_id = data.get(
        "session_id",
        ""
    ).strip()

    target = data.get(
        "target",
        "azure"
    ).strip().lower()


    # ------------------------------------------------------
    # VALIDATE SESSION ID
    # ------------------------------------------------------

    if not session_id:

        return jsonify({

            "success": False,

            "message":
                "AWS source session is missing."

        }), 400


    # ------------------------------------------------------
    # VALIDATE TARGET
    # ------------------------------------------------------

    if target != AZURE_TARGET:
        return jsonify(success=False, message="This assistant supports AWS source to Azure target only."), 400


    # ------------------------------------------------------
    # GET AWS SESSION
    # ------------------------------------------------------

    migration = owned_aws_session(
        session_id
    )


    if not migration:

        return jsonify({

            "success": False,

            "message":
                "AWS source session expired. "
                "Please connect AWS again."

        }), 401


    # ------------------------------------------------------
    # SCAN AWS RESOURCES
    # ------------------------------------------------------

    try:

        from app.services.aws_service import scan_resources

        result = scan_resources(session_id, target, user_id=current_user.id)


        if result.get("success"):

            return jsonify(
                result
            )


        return jsonify(
            result
        ), 500


    except Exception:

        current_app.logger.error(
            "aws_scan_failed user_id=%s operation=scan category=cloud",
            current_user.id,
        )


        return jsonify({

            "success": False,

            "message":
                "AWS resource scanning failed."

        }), 500


# ==========================================================
# PERSISTED MIGRATION PLANS
# ==========================================================

@migration_bp.route("/api/migration-plans", methods=["POST"])
def create_migration_plan():
    """Create an owner-scoped assessment plan from a fresh source-cloud scan."""
    data = request.get_json(silent=True) or {}
    source_session_id = str(data.get("source_session_id", "")).strip()
    target_session_id = str(data.get("target_session_id", "")).strip()
    source_cloud = str(data.get("source_cloud", "aws")).strip().lower()
    target_cloud = str(data.get("target_cloud", "azure")).strip().lower()
    if (source_cloud, target_cloud) != (AWS_SOURCE, AZURE_TARGET):
        return jsonify(success=False, message="This assistant supports AWS source to Azure target only."), 400
    if not source_session_id or not target_session_id:
        return jsonify(success=False, message="Source and target cloud sessions are required."), 400
    owned_aws_session(source_session_id)
    owned_azure_session(target_session_id)
    try:
        from app.services.aws_service import scan_resources
        scan_result = scan_resources(source_session_id, target_cloud, user_id=current_user.id)
        if not scan_result.get("success"):
            return jsonify(success=False, message="Cloud discovery is required before generating a plan."), 400
        plan = generate_migration_plan(
            user_id=current_user.id,
            source_cloud=source_cloud,
            target_cloud=target_cloud,
            source_session_reference=source_session_id,
            target_session_reference=target_session_id,
            normalized_resources=scan_result.get("resources", {}),
        )
        audit_event("migration_plan_generated", user_id=current_user.id,
                    status=plan.status, category="migration")
        return jsonify(success=True, plan=serialize_plan(plan)), 201
    except ValueError as error:
        return jsonify(success=False, message=str(error)), 400
    except Exception:
        current_app.logger.error("migration_plan_generation_failed user_id=%s operation=plan category=unexpected", current_user.id)
        return jsonify(success=False, message="Migration plan generation failed."), 500


@migration_bp.route("/api/migration-plans", methods=["GET"])
def list_migration_plans():
    plans = list_user_plans(current_user.id)
    return jsonify(success=True, plans=[serialize_plan(plan, include_resources=False) for plan in plans])


@migration_bp.route("/api/migration-plans/<string:plan_id>", methods=["GET"])
def get_migration_plan(plan_id):
    return jsonify(success=True, plan=serialize_plan(owned_migration_plan(plan_id)))


# ==========================================================
# START S3 MIGRATION
# ==========================================================

@migration_bp.route(
    "/api/migration/s3/start",
    methods=["POST"]
)
def start_s3_migration():

    data = request.get_json(
        silent=True
    ) or {}

    # ======================================================
    # GET SESSION IDS
    # ======================================================

    source_session_id = (
        data.get(
            "source_session_id",
            ""
        )
        .strip()
    )

    target_session_id = (
        data.get(
            "target_session_id",
            ""
        )
        .strip()
    )

    # ======================================================
    # GET BUCKET
    # ======================================================

    bucket_name = (
        data.get(
            "bucket_name",
            ""
        )
        .strip()
    )

    # ======================================================
    # GET CONFIGURATION
    # ======================================================

    configuration = (
        data.get(
            "configuration"
        )
        or {}
    )

    if not safe_migration_configuration(configuration):
        return jsonify({
            "success": False,
            "message": "Migration configuration is invalid."
        }), 400

    plan_reference = str(data.get("plan_id", "")).strip()

    # ======================================================
    # VALIDATE SOURCE SESSION
    # ======================================================

    if not source_session_id:

        return jsonify({
            "success": False,
            "message":
                "Source cloud session is missing."
        }), 400

    # ======================================================
    # VALIDATE TARGET SESSION
    # ======================================================

    if not target_session_id:

        return jsonify({
            "success": False,
            "message":
                "Target cloud session is missing."
        }), 400

    # ======================================================
    # VALIDATE BUCKET
    # ======================================================

    if not bucket_name or not valid_s3_bucket_name(bucket_name):

        return jsonify({
            "success": False,
            "message":
                "A valid S3 bucket name is required."
        }), 400

    plan = None
    if plan_reference:
        plan = owned_migration_plan(plan_reference)
        if plan.source_cloud != "aws" or plan.target_cloud != "azure":
            return jsonify(success=False, message="The selected plan is not an AWS to Azure plan."), 400
        s3_resource = next((resource for resource in plan.resources
                            if resource.service == "S3" and resource.resource_name == bucket_name), None)
        if not s3_resource or s3_resource.capability_classification != "supported_execution":
            return jsonify(success=False, message="The selected plan does not approve this bucket for supported execution."), 400

    # ======================================================
    # GET AWS SESSION
    # ======================================================

    migration = owned_aws_session(
        source_session_id
    )

    if not migration:

        return jsonify({
            "success": False,
            "message":
                "AWS source session expired. "
                "Please connect AWS again."
        }), 401

    aws_session = migration.get(
        "aws_session"
    )

    if not aws_session:

        return jsonify({
            "success": False,
            "message":
                "AWS session is unavailable."
        }), 401

    # ======================================================
    # GET AZURE SESSION
    # ======================================================

    target_migration = owned_azure_session(
        target_session_id
    )

    if not target_migration:

        return jsonify({
            "success": False,
            "message":
                "Azure target session expired. "
                "Please connect Azure again."
        }), 401

    # ======================================================
    # IMPORT MIGRATION SERVICE
    # ======================================================

    try:

        from app.services.s3_migration_service import start_s3_migration

        # ==================================================
        # START REAL S3 → AZURE MIGRATION
        # ==================================================

        result = start_s3_migration(

            aws_session,

            target_migration,

            bucket_name,

            configuration,
            user_id=current_user.id,
            plan_id=plan.id if plan else None,

        )

        # ==================================================
        # RETURN RESULT
        # ==================================================

        if result.get("success"):

            audit_event(
                "s3_migration_started",
                user_id=current_user.id,
                migration_id=result.get("migration_id"),
                status=result.get("status", "preparing"),
                category="migration"
            )

            return jsonify(public_migration_result(result)), 202

        return jsonify(public_migration_result(result)), 400

    except Exception:

        current_app.logger.error(
            "s3_migration_failed user_id=%s operation=transfer category=cloud",
            current_user.id,
        )

        return jsonify({

            "success": False,

            "message":
                "S3 to Azure migration could not be started."

        }), 500


@migration_bp.route("/api/migration/lambda/start", methods=["POST"])
def start_lambda_migration():
    """Deploy only the documented real Python-ZIP Lambda subset."""
    data = request.get_json(silent=True) or {}
    source_session_id = str(data.get("source_session_id", "")).strip()
    target_session_id = str(data.get("target_session_id", "")).strip()
    function_name = str(data.get("function_name", "")).strip()
    plan_reference = str(data.get("plan_id", "")).strip()
    configuration = data.get("configuration") or {}
    if not source_session_id or not target_session_id or not function_name or not isinstance(configuration, dict):
        return jsonify(success=False, message="Source, target, Lambda function, and deployment configuration are required."), 400
    if len(function_name) > 64 or not function_name.replace("-", "").replace("_", "").isalnum():
        return jsonify(success=False, message="Lambda function name has an invalid format."), 400
    if set(configuration) - {"resource_group", "function_app_name", "deployment_slot"}:
        return jsonify(success=False, message="Lambda deployment configuration contains unsupported fields."), 400
    source = owned_aws_session(source_session_id)
    target = owned_azure_session(target_session_id)
    if not plan_reference:
        return jsonify(success=False, message="Review and approve a persisted migration plan before Lambda deployment."), 400
    plan = owned_migration_plan(plan_reference)
    if plan.source_cloud != "aws" or plan.target_cloud != "azure" or \
            not any(item.service == "Lambda" and item.resource_name == function_name for item in plan.resources):
        return jsonify(success=False, message="The selected plan does not contain this AWS Lambda resource."), 400
    from app.services.lambda_migration_service import deploy_lambda, valid_deployment_configuration
    if not valid_deployment_configuration(configuration):
        return jsonify(success=False, message="Azure target identifiers have an invalid format."), 400
    try:
        approve_lambda_execution_target(plan, function_name, configuration)
    except ValueError as exc:
        return jsonify(success=False, message=str(exc)), 400
    result = deploy_lambda(source.get("aws_session"), target, function_name, configuration, current_user.id, plan.id)
    if result.get("success"):
        event = "lambda_migration_completed" if result.get("status") == "completed" else "lambda_migration_reused"
        audit_event(event, user_id=current_user.id, migration_id=result.get("migration_id"), status=result.get("status"), category="migration")
        return jsonify(public_migration_result(result)), 202
    audit_event("lambda_migration_not_started", user_id=current_user.id, migration_id=result.get("migration_id"), status=result.get("status"), category="migration")
    return jsonify(public_migration_result(result) | {"reasons": result.get("reasons", [])}), 400


@migration_bp.route("/api/migrations/<string:migration_id>", methods=["GET"])
def migration_status(migration_id):
    """Expose persisted migration state only to its owner."""
    migration = Migration.query.filter_by(migration_id=migration_id).first()
    if not migration:
        abort(404)
    if migration.user_id != current_user.id:
        abort(403)
    return jsonify({"success": True, "migration": migration_progress(migration)})


@migration_bp.route("/api/migrations/<string:migration_id>/report", methods=["GET"])
def migration_report(migration_id):
    """Persist and return an owner-scoped aggregate execution report."""
    migration = Migration.query.filter_by(migration_id=migration_id).first()
    if not migration:
        abort(404)
    if migration.user_id != current_user.id:
        abort(403)
    report = generate_report(migration)
    audit_event("migration_report_generated", user_id=current_user.id,
                migration_id=migration_id, status=migration.status, category="report")
    return jsonify(success=True, **serialize_report(report))


@migration_bp.route("/api/migrations", methods=["GET"])
def migration_history():
    """Return only the authenticated user's safe migration history."""
    migrations = Migration.query.filter_by(user_id=current_user.id).order_by(Migration.created_at.desc()).all()
    return jsonify(success=True, migrations=[public_migration_result(migration_progress(item)) for item in migrations])


@migration_bp.route("/migration/history")
def migration_history_page():
    migrations = Migration.query.filter_by(user_id=current_user.id).order_by(Migration.created_at.desc()).all()
    return render_template("migration/history.html", migrations=migrations)


@migration_bp.route("/migration/<string:migration_id>/details")
def migration_details_page(migration_id):
    migration = Migration.query.filter_by(migration_id=migration_id, user_id=current_user.id).first()
    if not migration:
        abort(404)
    report = generate_report(migration)
    records = MigrationFile.query.filter_by(migration_id=migration.id).order_by(MigrationFile.batch_number, MigrationFile.id).limit(200).all()
    return render_template("migration/details.html", migration=migration, report=serialize_report(report)["report"], records=records)


@migration_bp.route("/api/migrations/<string:migration_id>/objects", methods=["GET"])
def migration_object_results(migration_id):
    """Owner-scoped object results. Pagination avoids unbounded browser output."""
    migration = Migration.query.filter_by(migration_id=migration_id, user_id=current_user.id).first()
    if not migration:
        abort(404)
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        return jsonify(success=False, message="Page must be a positive number."), 400
    per_page = 100
    query = MigrationFile.query.filter_by(migration_id=migration.id).order_by(MigrationFile.batch_number, MigrationFile.id)
    records = query.offset((page - 1) * per_page).limit(per_page).all()
    return jsonify(success=True, page=page, objects=[{
        "object_key": item.object_key, "size_bytes": item.size_bytes, "batch_number": item.batch_number,
        "status": item.status, "verification_status": item.verification_status,
        "attempt_count": item.attempt_count, "bytes_transferred": item.bytes_transferred,
        "error": item.error_message,
    } for item in records])


@migration_bp.route("/api/migrations/<string:migration_id>/resume", methods=["POST"])
def resume_migration(migration_id):
    """Resume an owned interrupted S3 transfer with newly connected clouds."""
    migration = Migration.query.filter_by(migration_id=migration_id).first()
    if not migration:
        abort(404)
    if migration.user_id != current_user.id:
        abort(403)
    data = request.get_json(silent=True) or {}
    source_session_id = str(data.get("source_session_id", "")).strip()
    target_session_id = str(data.get("target_session_id", "")).strip()
    if not source_session_id or not target_session_id:
        return jsonify(success=False, message="Reconnect both clouds before resuming."), 400
    source = owned_aws_session(source_session_id)
    target = owned_azure_session(target_session_id)
    aws_session = source.get("aws_session")
    if not aws_session:
        return jsonify(success=False, message="AWS session is unavailable."), 401
    result = resume_s3_migration(migration, aws_session, target)
    if result.get("success"):
        audit_event("s3_migration_resume_started", user_id=current_user.id,
                    migration_id=migration_id, status=result.get("status", "preparing"), category="migration")
        return jsonify(public_migration_result(result)), 202
    return jsonify(public_migration_result(result)), 400
