from sqlalchemy import inspect, text

from app.extensions import db
from app.models.migration import MigrationPlan, MigrationPlanResource
from app.models.report import Report
from app.security.audit_logger import AuditEvent

_COLUMNS = {
    "migrations": {
        "destination_resource_group": "VARCHAR(255)",
        "destination_storage_account": "VARCHAR(64)",
        "destination_container": "VARCHAR(63)",
        "target_region": "VARCHAR(64)",
        "transferred_bytes": "BIGINT NOT NULL DEFAULT 0",
        "plan_id": "INTEGER",
        "active_identity": "VARCHAR(64)",
        "destination_provisioning_mode": "VARCHAR(32)",
        "execution_configuration": "TEXT NOT NULL DEFAULT '{}'",
        "failure_reason": "VARCHAR(255)",
        "uncertain_external_operation": "BOOLEAN NOT NULL DEFAULT 0",
        "cancellation_requested": "BOOLEAN NOT NULL DEFAULT 0",
        "worker_token": "VARCHAR(64)",
        "lease_expires_at": "DATETIME",
        "last_heartbeat_at": "DATETIME",
        "retry_count": "INTEGER NOT NULL DEFAULT 0",
        "updated_at": "DATETIME",
    },
    "migration_files": {
        "source_etag": "VARCHAR(256)",
        "destination_etag": "VARCHAR(256)",
        "verification_status": "VARCHAR(40)",
        "attempt_count": "INTEGER NOT NULL DEFAULT 0",
        "last_attempt_at": "DATETIME",
        "bytes_transferred": "BIGINT NOT NULL DEFAULT 0",
    },
}


def upgrade_legacy_schema(connection=None):
    """Bring pre-Alembic application databases to the baseline schema safely."""
    bind = connection or db.engine
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())
    for table_name, columns in _COLUMNS.items():
        if table_name not in existing_tables:
            continue
        present = {column["name"] for column in inspector.get_columns(table_name)}
        for column_name, sql_type in columns.items():
            if column_name not in present:
                bind.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {sql_type}"))

    if "users" in existing_tables:
        MigrationPlan.__table__.create(bind=bind, checkfirst=True)
        MigrationPlanResource.__table__.create(bind=bind, checkfirst=True)
        Report.__table__.create(bind=bind, checkfirst=True)
        AuditEvent.__table__.create(bind=bind, checkfirst=True)

    if "migrations" in set(inspect(bind).get_table_names()):
        bind.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_migrations_active_identity "
            "ON migrations (active_identity)"
        ))
        bind.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_migrations_worker_token "
            "ON migrations (worker_token)"
        ))
        bind.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_migrations_lease_expires_at "
            "ON migrations (lease_expires_at)"
        ))
    if "migration_files" in set(inspect(bind).get_table_names()):

        try:
            bind.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_migration_files_object "
                "ON migration_files (migration_id, object_key)"
            ))
        except Exception:

            pass


def upgrade_phase2_migration_schema():
    """Backward-compatible public alias for older callers.

    New application code must use ``flask db upgrade`` rather than mutating
    schemas at startup.
    """
    with db.engine.begin() as connection:
        upgrade_legacy_schema(connection)
