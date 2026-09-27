"""Forward-only, additive schema updates for persisted migration state.

The project does not currently have an initialized Alembic repository.  This
small compatibility upgrade deliberately uses only ``ADD COLUMN`` after
inspecting the live schema; it never drops tables, recreates the SQLite file,
or changes existing migration rows.  It can be replaced by an Alembic revision
once the application adopts a full migration repository.
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


def upgrade_phase2_migration_schema():
    """Safely add Phase 2 columns to databases created before this release."""
    inspector = inspect(db.engine)
    existing_tables = set(inspector.get_table_names())
    for table_name, columns in _COLUMNS.items():
        if table_name not in existing_tables:
            continue
        present = {column["name"] for column in inspector.get_columns(table_name)}
        for column_name, sql_type in columns.items():
            if column_name not in present:
                db.session.execute(
                    text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {sql_type}")
                )
    db.session.commit()

    # Migration plans are new additive tables.  Creating them with checkfirst
    # preserves all existing user, migration, and migration-file records.
    if "users" in existing_tables:
        MigrationPlan.__table__.create(bind=db.engine, checkfirst=True)
        MigrationPlanResource.__table__.create(bind=db.engine, checkfirst=True)
        Report.__table__.create(bind=db.engine, checkfirst=True)
        AuditEvent.__table__.create(bind=db.engine, checkfirst=True)

    # Historical records receive NULL active identities and remain compatible.
    if "migrations" in set(inspect(db.engine).get_table_names()):
        db.session.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_migrations_active_identity "
            "ON migrations (active_identity)"
        ))
    if "migration_files" in set(inspect(db.engine).get_table_names()):
        # Existing historical duplicate rows must not be deleted by an
        # upgrade. New databases receive the model-level unique constraint.
        try:
            db.session.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_migration_files_object "
                "ON migration_files (migration_id, object_key)"
            ))
        except Exception:
            db.session.rollback()
    db.session.commit()
