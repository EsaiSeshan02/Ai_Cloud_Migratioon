"""Forward-only compatibility helpers used by the Alembic baseline.

The helpers deliberately add missing legacy columns and indexes only. They
never drop, recreate, or delete application data. New databases are created
from SQLAlchemy metadata by the baseline revision.
"""

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

    # Migration plans are new additive tables.  Creating them with checkfirst
    # preserves all existing user, migration, and migration-file records.
    if "users" in existing_tables:
        MigrationPlan.__table__.create(bind=bind, checkfirst=True)
        MigrationPlanResource.__table__.create(bind=bind, checkfirst=True)
        Report.__table__.create(bind=bind, checkfirst=True)
        AuditEvent.__table__.create(bind=bind, checkfirst=True)

    # Historical records receive NULL active identities and remain compatible.
    if "migrations" in set(inspect(bind).get_table_names()):
        bind.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_migrations_active_identity "
            "ON migrations (active_identity)"
        ))
    if "migration_files" in set(inspect(bind).get_table_names()):
        # Existing historical duplicate rows must not be deleted by an
        # upgrade. New databases receive the model-level unique constraint.
        try:
            bind.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_migration_files_object "
                "ON migration_files (migration_id, object_key)"
            ))
        except Exception:
            # Existing duplicate historical rows prevent a unique index.
            # Preserve them and let the operator resolve them before retrying.
            pass


def upgrade_phase2_migration_schema():
    """Backward-compatible public alias for older callers.

    New application code must use ``flask db upgrade`` rather than mutating
    schemas at startup.
    """
    with db.engine.begin() as connection:
        upgrade_legacy_schema(connection)
