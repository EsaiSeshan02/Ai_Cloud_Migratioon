"""Persisted, streaming S3-to-Azure-Blob migration support.

Each object is read from S3's streaming body and passed directly to Azure.
The 10 GB batches are logical scheduling groups, never in-memory buffers.
"""
import hashlib
import json
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from collections import defaultdict

from botocore.exceptions import ClientError, EndpointConnectionError
from azure.core.exceptions import AzureError, ResourceExistsError, ResourceNotFoundError
from azure.mgmt.storage import StorageManagementClient
from azure.storage.blob import BlobServiceClient
from flask import current_app
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.migration import Migration, MigrationFile
from app.security.logging_utils import log_event

GB = 1024 * 1024 * 1024
BATCH_SIZE_LIMIT = 10 * GB
DEFAULT_CONTAINER_NAME = "migrated-data"
MAX_TRANSFER_ATTEMPTS = 3
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="s3-migration")
_active_migrations = set()

# These states describe persisted execution, not simulated progress.  A
# browser may safely poll ``preparing`` while a worker is queued.
_ACTIVE_STATES = {"preparing", "running"}
_RESUMABLE_STATES = {"interrupted", "failed", "completed_with_failures"}
_TERMINAL_STATES = {"completed", "completed_with_review", "cancelled"}
_TERMINAL_FILE_STATES = {"verified", "skipped", "failed", "manual_review"}
_ALLOWED_TRANSITIONS = {
    "pending": {"preparing"},
    "preparing": {"running", "interrupted", "failed", "completed", "cancelled"},
    "running": {"interrupted", "failed", "completed", "completed_with_failures", "completed_with_review"},
    # Direct synchronous execution is retained for the existing compatibility
    # wrapper and can safely continue an interrupted persisted migration.
    "interrupted": {"preparing", "running"},
    "failed": {"preparing", "running"},
    "completed_with_failures": {"preparing", "running"},
    "completed": set(),
    "completed_with_review": set(),
    "cancelled": set(),
}


def _transition(migration, new_status):
    """Apply only an explicit, persisted S3 migration state transition."""
    current = migration.status
    if current == new_status:
        return True
    if new_status not in _ALLOWED_TRANSITIONS.get(current, set()):
        return False
    migration.status = new_status
    # Interrupted and failed records retain their identity so a subsequent
    # start cannot silently create competing work; the owner must resume or
    # explicitly resolve the persisted migration.
    if new_status in _TERMINAL_STATES:
        migration.active_identity = None
    return True


def _active_identity(user_id, bucket_name, azure_session, configuration):
    """Hash non-secret source/destination identity for database idempotency."""
    configuration = configuration if isinstance(configuration, dict) else {}
    destination = "|".join((
        str(azure_session.get("subscription_id", "")),
        str(configuration.get("destination_resource_group", "")).strip().lower(),
        str(configuration.get("destination_storage_account", "")).strip().lower(),
        _safe_container_name(configuration.get("container_name")),
        str(configuration.get("target_region", "centralindia")).strip().lower(),
    ))
    return hashlib.sha256(
        f"{user_id}|aws|azure|{str(bucket_name).strip().lower()}|{destination}".encode("utf-8")
    ).hexdigest()


def _safe_execution_configuration(configuration):
    """Persist destination intent only; credentials are never configuration."""
    configuration = configuration if isinstance(configuration, dict) else {}
    allowed = {"container_name", "target_region", "destination_resource_group",
               "destination_storage_account", "provision_destination"}
    return {key: configuration[key] for key in allowed if configuration.get(key) not in (None, "")}


def get_s3_objects(session, bucket_name):
    """List metadata only; no object content is read at this stage."""
    try:
        objects = []
        for page in session.client("s3").get_paginator("list_objects_v2").paginate(Bucket=bucket_name):
            for obj in page.get("Contents", []):
                objects.append({"key": obj["Key"], "size": obj["Size"],
                                "etag": (obj.get("ETag") or "").strip('"') or None})
        return {"success": True, "objects": objects}
    except (ClientError, EndpointConnectionError):
        current_app.logger.error("s3_list_failed operation=list category=cloud")
        return {"success": False, "message": "S3 object discovery failed."}
    except Exception:
        current_app.logger.error("s3_list_failed operation=list category=unexpected")
        return {"success": False, "message": "S3 object discovery failed."}


def create_batches(objects):
    """Group metadata into logical batches of at most roughly 10 GB."""
    batches, batch, batch_size = [], [], 0
    for obj in objects:
        size = int(obj["size"])
        if batch and batch_size + size > BATCH_SIZE_LIMIT:
            batches.append({"batch_number": len(batches) + 1, "files": batch, "size": batch_size})
            batch, batch_size = [], 0
        batch.append(obj)
        batch_size += size
    if batch:
        batches.append({"batch_number": len(batches) + 1, "files": batch, "size": batch_size})
    return batches


def _safe_container_name(value):
    value = re.sub(r"[^a-z0-9-]", "-", str(value or DEFAULT_CONTAINER_NAME).lower()).strip("-")
    return value[:63] or DEFAULT_CONTAINER_NAME


def _storage_key(azure_session, resource_group, storage_account):
    client = StorageManagementClient(azure_session["credential"], azure_session["subscription_id"])
    result = client.storage_accounts.list_keys(resource_group, storage_account)
    keys = result.as_dict().get("keys", []) if hasattr(result, "as_dict") else getattr(result, "keys", [])
    if not keys:
        raise AzureError("Storage account did not provide an access key")
    first = keys[0]
    return first.get("value") if isinstance(first, dict) else getattr(first, "value", None)


def _first_resource_group(azure_session):
    group = next(iter(azure_session["resource_client"].resource_groups.list()), None)
    if not group:
        raise AzureError("No Azure resource group is available")
    return group.name


def _create_destination(azure_session, resource_group, region, bucket_name):
    account = "aicm" + re.sub(r"[^a-z0-9]", "", bucket_name.lower())[:12] + uuid.uuid4().hex[:8]
    client = StorageManagementClient(azure_session["credential"], azure_session["subscription_id"])
    client.storage_accounts.begin_create(resource_group, account, {
        "location": region, "kind": "StorageV2", "sku": {"name": "Standard_LRS"}
    }).result()
    return account


def _destination_from_configuration(azure_session, migration, configuration, bucket_name):
    """Resolve an explicitly selected destination or an intentional auto-provision.

    Legacy flows retain automatic provisioning, but the persisted migration
    records which mode was used so reports and the UI cannot imply that a
    destination was silently chosen.
    """
    configuration = configuration if isinstance(configuration, dict) else {}
    resource_group = str(configuration.get("destination_resource_group") or "").strip()
    account = str(configuration.get("destination_storage_account") or "").strip()
    region = str(configuration.get("target_region") or "centralindia").strip().lower()
    if bool(resource_group) != bool(account):
        raise ValueError("Destination resource group and storage account must be supplied together.")
    if account:
        migration.destination_provisioning_mode = "selected_existing"
        return resource_group, account, region
    if configuration.get("provision_destination") in {False, "false", "False", 0}:
        raise ValueError("Select an Azure Storage Account or explicitly allow destination provisioning.")
    resource_group = _first_resource_group(azure_session)
    migration.destination_provisioning_mode = "automatic_provisioning"
    return resource_group, _create_destination(azure_session, resource_group, region, bucket_name), region


def _container_client(azure_session, migration):
    key = _storage_key(azure_session, migration.destination_resource_group, migration.destination_storage_account)
    endpoint = f"https://{migration.destination_storage_account}.blob.core.windows.net"
    container = BlobServiceClient(account_url=endpoint, credential=key).get_container_client(migration.destination_container)
    try:
        container.create_container()
    except ResourceExistsError:
        pass
    return container


def _refresh_counts(migration):
    records = MigrationFile.query.filter_by(migration_id=migration.id).all()
    migration.uploaded_files = sum(item.status in {"verified", "skipped"} for item in records)
    migration.failed_files = sum(item.status == "failed" for item in records)
    migration.transferred_bytes = sum(
        int(item.bytes_transferred or 0) for item in records if item.status == "verified"
    )


def _set_file_result(record, status, message=None, verification=None, destination_etag=None, bytes_transferred=0):
    record.status = status
    record.error_message = message
    record.verification_status = verification
    record.destination_etag = destination_etag
    record.bytes_transferred = int(bytes_transferred or 0) if status == "verified" else 0
    if status in {"verified", "skipped", "failed", "manual_review"}:
        record.completed_at = datetime.utcnow()


def _blob_size_and_etag(blob_client):
    properties = blob_client.get_blob_properties()
    return int(properties.size), str(getattr(properties, "etag", "") or "")


def _is_transient(error):
    if isinstance(error, EndpointConnectionError):
        return True
    if isinstance(error, ClientError):
        return str(error.response.get("Error", {}).get("Code", "")) in {
            "RequestTimeout", "SlowDown", "Throttling", "ServiceUnavailable", "InternalError"
        }
    return isinstance(error, AzureError) and not isinstance(error, (ResourceExistsError, ResourceNotFoundError))


def _transfer_one(s3_client, bucket_name, record, container_client):
    """Stream and size-verify one object; Azure SDK controls transport chunks.

    The application's 10 GB batches are logical scheduling groups.  This
    function passes the S3 streaming body to the Azure SDK and never buffers
    a full object or claims a cross-provider cryptographic checksum.
    """
    blob_client = container_client.get_blob_client(record.object_key)
    try:
        size, etag = _blob_size_and_etag(blob_client)
        if size == record.size_bytes:
            return "skipped", None, "size_matched_existing", etag, 0
        return "manual_review", "A destination object with a different size already exists.", "size_mismatch", etag, 0
    except ResourceNotFoundError:
        pass
    except AzureError:
        return "failed", "Destination object could not be inspected.", None, None, 0

    last_error = None
    for attempt in range(1, MAX_TRANSFER_ATTEMPTS + 1):
        body = None
        try:
            record.attempt_count = (record.attempt_count or 0) + 1
            record.last_attempt_at = datetime.utcnow()
            # Persist retry evidence before making a provider request so a
            # restart does not erase the fact that a transfer was attempted.
            db.session.commit()
            response = s3_client.get_object(Bucket=bucket_name, Key=record.object_key)
            body = response["Body"]
            source_size = int(response.get("ContentLength", record.size_bytes))
            source_etag = (response.get("ETag") or "").strip('"') or record.source_etag
            if source_size != record.size_bytes:
                return "manual_review", "The source object changed after preparation.", "source_changed", None, 0
            if record.source_etag and source_etag and record.source_etag != source_etag:
                return "manual_review", "The source object changed after preparation.", "source_changed", None, 0
            blob_client.upload_blob(body, overwrite=False)
            destination_size, destination_etag = _blob_size_and_etag(blob_client)
            if destination_size != source_size:
                return "failed", "Destination size verification failed.", "size_mismatch", destination_etag, 0
            record.source_etag = source_etag
            return "verified", None, "size_verified", destination_etag, source_size
        except ResourceExistsError:
            try:
                destination_size, destination_etag = _blob_size_and_etag(blob_client)
                if destination_size == record.size_bytes:
                    return "skipped", None, "size_matched_existing", destination_etag, 0
                return "manual_review", "A destination object with a different size already exists.", "size_mismatch", destination_etag, 0
            except AzureError:
                return "failed", "Destination object could not be verified.", None, None, 0
        except (ClientError, EndpointConnectionError, AzureError) as error:
            last_error = error
            if not _is_transient(error) or attempt == MAX_TRANSFER_ATTEMPTS:
                break
            time.sleep(2 ** (attempt - 1))
        finally:
            if body is not None:
                body.close()
    if last_error:
        current_app.logger.warning("s3_object_transfer_failed operation=transfer category=cloud")
    return "failed", "Object transfer failed after bounded retries.", None, None, 0


def _finalize(migration):
    _refresh_counts(migration)
    statuses = {item.status for item in MigrationFile.query.filter_by(migration_id=migration.id).all()}
    if not statuses or statuses <= {"verified", "skipped"}:
        final_status = "completed"
    elif "failed" in statuses:
        final_status = "completed_with_failures" if migration.uploaded_files else "failed"
    elif "manual_review" in statuses:
        final_status = "completed_with_review"
    else:
        final_status = "failed"
    if not _transition(migration, final_status):
        current_app.logger.error("s3_invalid_state_transition operation=finalize category=state")
        return False
    migration.completed_at = datetime.utcnow()
    db.session.commit()
    return True


def migration_progress(migration):
    records = MigrationFile.query.filter_by(migration_id=migration.id).all()
    status_counts = defaultdict(int)
    batch_statuses = defaultdict(list)
    retry_attempts = 0
    for record in records:
        status_counts[record.status] += 1
        batch_statuses[record.batch_number].append(record.status)
        retry_attempts += int(record.attempt_count or 0)
    transferred_bytes = sum(
        int(record.bytes_transferred or 0)
        for record in records if record.status == "verified"
    )
    completed_batches = sum(
        all(status in _TERMINAL_FILE_STATES for status in statuses)
        for statuses in batch_statuses.values()
    )
    current_batch = next(
        (number for number in sorted(batch_statuses)
         if not all(status in _TERMINAL_FILE_STATES for status in batch_statuses[number])),
        None,
    )
    return {
        "success": migration.status == "completed",
        "migration_id": migration.migration_id,
        "status": migration.status,
        "total_files": migration.total_files,
        "uploaded_files": migration.uploaded_files,
        "failed_files": migration.failed_files,
        "verified_files": status_counts["verified"],
        "skipped_files": status_counts["skipped"],
        "manual_review_files": status_counts["manual_review"],
        "pending_files": status_counts["pending"],
        "transferring_files": status_counts["transferring"],
        "processed_files": status_counts["verified"] + status_counts["skipped"] + status_counts["manual_review"] + status_counts["failed"],
        "total_size_bytes": migration.total_size_bytes,
        "transferred_bytes": transferred_bytes,
        "total_batches": migration.total_batches,
        "completed_batches": completed_batches,
        "current_batch": current_batch,
        "retry_attempts": retry_attempts,
        "retriable_files": status_counts["failed"] + status_counts["transferring"],
        "logical_batch_size_bytes": BATCH_SIZE_LIMIT,
    }


def execute_s3_migration(migration_id, aws_session, azure_session):
    """Execute pending/failed records; safe to invoke again for a resume."""
    migration = Migration.query.filter_by(migration_id=migration_id, resource_type="s3").first()
    if not migration:
        return {"success": False, "message": "Migration was not found."}
    if migration.status not in _ACTIVE_STATES | _RESUMABLE_STATES:
        return {"success": False, "migration_id": migration_id, "message": "Migration is not in a runnable state."}
    try:
        if not _transition(migration, "running"):
            return {"success": False, "migration_id": migration_id, "message": "Migration state transition was rejected."}
        migration.started_at = migration.started_at or datetime.utcnow()
        db.session.commit()
        s3_client, container_client = aws_session.client("s3"), _container_client(azure_session, migration)
        records = MigrationFile.query.filter_by(migration_id=migration.id).order_by(MigrationFile.batch_number, MigrationFile.id).all()
        for record in records:
            if record.status in {"verified", "skipped", "manual_review"}:
                continue
            if record.status == "completed":
                _set_file_result(record, "manual_review", "Legacy completion has no persisted verification evidence.", "legacy_unverified")
                db.session.commit()
                continue
            record.status = "transferring"
            record.started_at = record.started_at or datetime.utcnow()
            record.error_message = None
            db.session.commit()
            status, message, verification, destination_etag, transferred = _transfer_one(s3_client, migration.resource_name, record, container_client)
            _set_file_result(record, status, message, verification, destination_etag, transferred)
            _refresh_counts(migration)
            db.session.commit()
        if not _finalize(migration):
            return {"success": False, "migration_id": migration_id, "message": "Migration finalization was rejected."}
        log_event(current_app.logger, "s3_migration_finished", user_id=migration.user_id,
                  migration_id=migration.migration_id, operation="transfer", status=migration.status)
        return migration_progress(migration)
    except Exception:
        db.session.rollback()
        current_app.logger.error("s3_migration_failed migration_id=%s operation=transfer category=unexpected", migration_id)
        migration = Migration.query.filter_by(migration_id=migration_id).first()
        if migration and _transition(migration, "interrupted"):
            db.session.commit()
        return {"success": False, "migration_id": migration_id, "message": "Migration was interrupted and can be resumed."}


def _prepare_migration(aws_session, azure_session, bucket_name, configuration, user_id, plan_id=None):
    # A repeated start request must not create competing migrations for the
    # same owner and bucket while persisted work is still active.
    identity = _active_identity(user_id, bucket_name, azure_session, configuration)
    existing = Migration.query.filter_by(active_identity=identity).first()
    if not existing:
        # Compatibility for records created before active identities existed.
        existing = Migration.query.filter(
            Migration.user_id == user_id,
            Migration.source_cloud == "aws",
            Migration.target_cloud == "azure",
            Migration.resource_type == "s3",
            Migration.resource_name == bucket_name,
            Migration.status.in_(_ACTIVE_STATES),
        ).order_by(Migration.created_at.desc()).first()
    if existing:
        result = migration_progress(existing)
        # This internal marker distinguishes an existing ``preparing`` record
        # from a new one.  Both legitimately have the same persisted status,
        # but only a new record may be queued below.
        result.update({
            "success": True,
            "message": ("An existing migration is already active for this bucket."
                        if existing.status in _ACTIVE_STATES
                        else "An existing migration must be resumed or reviewed before starting another."),
            "_existing_active": True,
        })
        return result
    listed = get_s3_objects(aws_session, bucket_name)
    if not listed["success"]:
        return listed
    objects = []
    seen_keys = set()
    for obj in listed["objects"]:
        if obj["key"] not in seen_keys:
            seen_keys.add(obj["key"])
            objects.append(obj)
    batches = create_batches(objects)
    migration = Migration(migration_id=uuid.uuid4().hex, user_id=user_id, plan_id=plan_id,
                          active_identity=identity, source_cloud="aws", target_cloud="azure",
                          resource_type="s3", resource_name=bucket_name, status="preparing", total_files=len(objects),
                          total_size_bytes=sum(obj["size"] for obj in objects), total_batches=len(batches),
                          execution_configuration=json.dumps(_safe_execution_configuration(configuration), separators=(",", ":")),
                          started_at=datetime.utcnow())
    db.session.add(migration)
    try:
        db.session.flush()
        for batch in batches:
            for obj in batch["files"]:
                db.session.add(MigrationFile(migration_id=migration.id, object_key=obj["key"], size_bytes=obj["size"],
                                             batch_number=batch["batch_number"], source_etag=obj.get("etag")))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        existing = Migration.query.filter_by(active_identity=identity).first()
        if existing:
            result = migration_progress(existing)
            result.update({"success": True, "message": "An existing migration is already active for this bucket.",
                           "_existing_active": True})
            return result
        return {"success": False, "message": "Migration preparation conflicted with another request. Please retry."}
    try:
        if not objects:
            _transition(migration, "completed")
            migration.completed_at = datetime.utcnow()
            db.session.commit()
            return migration_progress(migration)
        resource_group, account, region = _destination_from_configuration(azure_session, migration, configuration, bucket_name)
        migration.destination_resource_group = resource_group
        migration.destination_storage_account = account
        migration.destination_container, migration.target_region = _safe_container_name(configuration.get("container_name")), region
        db.session.commit()
        return migration_progress(migration)
    except Exception:
        db.session.rollback()
        migration = Migration.query.filter_by(migration_id=migration.migration_id).first()
        if migration:
            if _transition(migration, "failed"):
                db.session.commit()
        current_app.logger.error("s3_destination_prepare_failed operation=storage category=cloud")
        return {"success": False, "migration_id": migration.migration_id, "message": "Migration destination preparation failed."}


def _run_in_app(app, migration_id, aws_session, azure_session):
    try:
        with app.app_context():
            execute_s3_migration(migration_id, aws_session, azure_session)
    finally:
        _active_migrations.discard(migration_id)


def start_s3_migration(aws_session, azure_session, bucket_name, configuration=None, user_id=None, plan_id=None):
    """Persist preparation first, then run the real transfer in a worker."""
    result = _prepare_migration(aws_session, azure_session, bucket_name, configuration or {}, user_id, plan_id=plan_id)
    if result.pop("_existing_active", False):
        # Never queue a second worker, initialise an Azure client, reset
        # counters, or alter object records for an already-active migration.
        return result
    if not result.get("migration_id"):
        return result
    migration_id = result["migration_id"]
    if result.get("status") != "preparing":
        return result
    if migration_id not in _active_migrations:
        _active_migrations.add(migration_id)
        _executor.submit(_run_in_app, current_app._get_current_object(), migration_id, aws_session, azure_session)
    result.update({"success": True, "message": "Migration prepared; transfer queued."})
    return result


def resume_s3_migration(migration, aws_session, azure_session):
    if migration.resource_type != "s3" or not migration.destination_storage_account:
        return {"success": False, "message": "This migration cannot be resumed automatically."}
    if migration.status == "completed":
        return migration_progress(migration)
    if migration.status in _TERMINAL_STATES:
        return {"success": False, "migration_id": migration.migration_id,
                "message": "Migration has manual-review outcomes and cannot be resumed automatically."}
    if migration.status in _ACTIVE_STATES:
        result = migration_progress(migration)
        result.update({"success": True, "message": "Migration is already active."})
        return result
    if migration.status not in _RESUMABLE_STATES:
        return {"success": False, "migration_id": migration.migration_id,
                "message": "Migration is not in a resumable state."}
    if not _transition(migration, "preparing"):
        return {"success": False, "migration_id": migration.migration_id,
                "message": "Migration state transition was rejected."}
    db.session.commit()
    if migration.migration_id not in _active_migrations:
        _active_migrations.add(migration.migration_id)
        _executor.submit(_run_in_app, current_app._get_current_object(), migration.migration_id, aws_session, azure_session)
    result = migration_progress(migration)
    result.update({"success": True, "message": "Migration resume prepared; transfer queued."})
    return result


def migrate_s3_to_azure(aws_session, azure_session, bucket_name, configuration=None, user_id=None, plan_id=None):
    """Compatibility wrapper for callers requiring synchronous migration."""
    prepared = _prepare_migration(aws_session, azure_session, bucket_name, configuration or {}, user_id, plan_id=plan_id)
    if not prepared.get("migration_id") or prepared.get("status") != "preparing":
        return prepared
    return execute_s3_migration(prepared["migration_id"], aws_session, azure_session)


def mark_incomplete_migrations_interrupted():
    """A restart leaves no falsely active migration state behind."""
    if "migrations" not in inspect(db.engine).get_table_names():
        return
    Migration.query.filter(Migration.status.in_(["preparing", "running"])).update(
        {Migration.status: "interrupted"}, synchronize_session=False
    )
    db.session.commit()
