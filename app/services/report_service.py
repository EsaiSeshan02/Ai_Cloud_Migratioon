"""Safe, persisted reports derived from real migration state only."""

import json
import uuid

from flask import current_app

from app.extensions import db
from app.models.migration import Migration, MigrationFile
from app.models.report import Report
from app.services.s3_migration_service import migration_progress
from app.utils.time import utc_now


def build_report_payload(migration):
    """Build an aggregate report without object keys or cloud credentials."""
    progress = migration_progress(migration)
    records = MigrationFile.query.filter_by(migration_id=migration.id).all()
    verification = {}
    for record in records:
        status = record.verification_status or "not_verified"
        verification[status] = verification.get(status, 0) + 1
    started = migration.started_at
    ended = migration.completed_at
    duration_seconds = None
    if started and ended:
        duration_seconds = max(0, int((ended - started).total_seconds()))
    payload = {
        "migration_id": migration.migration_id,
        "plan_id": migration.plan.plan_id if migration.plan else None,
        "source_cloud": migration.source_cloud,
        "target_cloud": migration.target_cloud,
        "resource_type": migration.resource_type,
        "resource_name": migration.resource_name,
        "destination": {
            "resource_group": migration.destination_resource_group,
            "storage_account": migration.destination_storage_account,
            "container": migration.destination_container,
            "region": migration.target_region,
            "provisioning_mode": migration.destination_provisioning_mode,
        },
        "status": migration.status,
        "cancellation_requested": bool(migration.cancellation_requested),
        "explicit_retry_count": int(migration.retry_count or 0),
        "failure_reason": migration.failure_reason,
        "started_at": started.isoformat() if started else None,
        "completed_at": ended.isoformat() if ended else None,
        "duration_seconds": duration_seconds,
        "total_objects": progress["total_files"],
        "verified_objects": progress["verified_files"],
        "skipped_objects": progress["skipped_files"],
        "failed_objects": progress["failed_files"],
        "manual_review_objects": progress["manual_review_files"],
        "bytes_transferred": progress["transferred_bytes"],
        "retry_attempts": progress["retry_attempts"],
        "verification_summary": verification,
        "verification_scope": "destination_size_and_metadata_verification",
        "uncertain_external_operation": bool(getattr(migration, "uncertain_external_operation", False)),
    }
    if migration.resource_type == "lambda":
        try:
            config = json.loads(migration.execution_configuration or "{}")
        except (TypeError, ValueError):
            config = {}
        payload["lambda_deployment"] = {
            key: config.get(key) for key in ("function_arn", "runtime", "handler", "function_app_name", "resource_group", "deployment_slot", "compatibility")
        }
        payload["lambda_deployment"]["failure_reason"] = migration.failure_reason
        payload["verification_scope"] = "Azure Function App management-plane validation after ZIP deployment"
    return payload


def generate_report(migration):
    """Create or refresh the sole report snapshot for a migration."""
    if not isinstance(migration, Migration):
        raise ValueError("A persisted migration is required.")
    report = Report.query.filter_by(migration_id=migration.id).first()
    if report is None:
        report = Report(report_id=uuid.uuid4().hex, user_id=migration.user_id,
                        migration_id=migration.id, plan_id=migration.plan_id,
                        status=migration.status)
        db.session.add(report)
    report.status = migration.status
    report.plan_id = migration.plan_id
    report.report_data = json.dumps(build_report_payload(migration), separators=(",", ":"))
    report.generated_at = utc_now()
    db.session.commit()
    return report


def generate_report_safely(migration):
    """Attempt post-outcome bookkeeping without changing the outcome.

    Execution state is committed before this helper is called.  A report is
    useful audit data, but a report-generation/database failure must never
    send control back through a provider-failure path or rewrite a terminal
    migration result.
    """
    try:
        return generate_report(migration)
    except Exception:
        db.session.rollback()
        current_app.logger.warning(
            "migration_report_generation_failed operation=report category=database"
        )
        return None


def current_report_snapshot(migration):
    """Read an existing report without mutating state.

    Pre-report historical migrations can still be viewed truthfully from their
    persisted execution state. New terminal executions create a report at the
    outcome boundary rather than during an HTTP GET.
    """
    report = Report.query.filter_by(migration_id=migration.id).first()
    if report is not None:
        return serialize_report(report)
    return {
        "report_id": None,
        "generated_at": None,
        "status": migration.status,
        "report": build_report_payload(migration),
    }


def serialize_report(report):
    try:
        payload = json.loads(report.report_data or "{}")
    except (TypeError, ValueError):
        payload = {}
    return {"report_id": report.report_id, "generated_at": report.generated_at.isoformat() if report.generated_at else None,
            "status": report.status, "report": payload}
