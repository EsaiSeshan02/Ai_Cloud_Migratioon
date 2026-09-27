"""Immutable baseline for the current persisted application schema.

Revision ID: 20260927_01
Revises:
Create Date: 2026-09-27
"""

from alembic import op
import sqlalchemy as sa

from app.database.migration_schema import upgrade_legacy_schema


revision = "20260927_01"
down_revision = None
branch_labels = None
depends_on = None


def _baseline_metadata():
    """Snapshot the schema; do not depend on future model changes."""
    metadata = sa.MetaData()
    sa.Table("users", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("email", sa.String(120), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    sa.Table("migration_plans", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("plan_id", sa.String(64), nullable=False, unique=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source_cloud", sa.String(20), nullable=False),
        sa.Column("target_cloud", sa.String(20), nullable=False),
        sa.Column("source_session_reference", sa.String(128)),
        sa.Column("target_session_reference", sa.String(128)),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("resource_count", sa.Integer, nullable=False),
        sa.Column("execution_ready_count", sa.Integer, nullable=False),
        sa.Column("planning_review_count", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Table("migrations", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("migration_id", sa.String(64), nullable=False, unique=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("plan_id", sa.Integer, sa.ForeignKey("migration_plans.id")),
        sa.Column("active_identity", sa.String(64), unique=True),
        sa.Column("source_cloud", sa.String(20), nullable=False),
        sa.Column("target_cloud", sa.String(20), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("total_files", sa.Integer, nullable=False, server_default="0"),
        sa.Column("uploaded_files", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failed_files", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_size_bytes", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("transferred_bytes", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("total_batches", sa.Integer, nullable=False, server_default="0"),
        sa.Column("destination_resource_group", sa.String(255)),
        sa.Column("destination_storage_account", sa.String(64)),
        sa.Column("destination_container", sa.String(63)),
        sa.Column("target_region", sa.String(64)),
        sa.Column("destination_provisioning_mode", sa.String(32)),
        sa.Column("execution_configuration", sa.Text, nullable=False, server_default="{}"),
        sa.Column("failure_reason", sa.String(255)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Table("migration_files", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("migration_id", sa.Integer, sa.ForeignKey("migrations.id"), nullable=False),
        sa.Column("object_key", sa.String(1024), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("batch_number", sa.Integer, nullable=False, server_default="1"),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("error_message", sa.Text),
        sa.Column("source_etag", sa.String(256)),
        sa.Column("destination_etag", sa.String(256)),
        sa.Column("verification_status", sa.String(40)),
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("bytes_transferred", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("migration_id", "object_key", name="uq_migration_file_object"),
    )
    sa.Table("migration_plan_resources", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("plan_id", sa.Integer, sa.ForeignKey("migration_plans.id"), nullable=False),
        sa.Column("source_cloud", sa.String(20), nullable=False),
        sa.Column("target_cloud", sa.String(20), nullable=False),
        sa.Column("service", sa.String(80), nullable=False),
        sa.Column("resource_id", sa.String(1024), nullable=False),
        sa.Column("resource_name", sa.String(1024), nullable=False),
        sa.Column("target_service", sa.String(160), nullable=False),
        sa.Column("capability_classification", sa.String(32), nullable=False),
        sa.Column("compatibility", sa.Integer, nullable=False, server_default="0"),
        sa.Column("execution_mode", sa.String(64), nullable=False),
        sa.Column("status", sa.String(160), nullable=False),
        sa.Column("risk_level", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("dependencies", sa.Text, nullable=False, server_default="[]"),
        sa.Column("preflight_findings", sa.Text, nullable=False, server_default="[]"),
        sa.Column("manual_review_reasons", sa.Text, nullable=False, server_default="[]"),
        sa.Column("recommendation_data", sa.Text, nullable=False, server_default="{}"),
        sa.Column("source_metadata", sa.Text, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Table("reports", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("report_id", sa.String(64), nullable=False, unique=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("migration_id", sa.Integer, sa.ForeignKey("migrations.id"), nullable=False, unique=True),
        sa.Column("plan_id", sa.Integer, sa.ForeignKey("migration_plans.id")),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("report_data", sa.Text, nullable=False, server_default="{}"),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Table("audit_events", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("event", sa.String(96), nullable=False),
        sa.Column("user_id", sa.Integer),
        sa.Column("migration_id", sa.String(64)),
        sa.Column("status", sa.String(48)),
        sa.Column("category", sa.String(48)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for name, table, column in (
        ("ix_migration_plans_plan_id", "migration_plans", "plan_id"),
        ("ix_migration_plans_user_id", "migration_plans", "user_id"),
        ("ix_migration_plan_resources_plan_id", "migration_plan_resources", "plan_id"),
        ("ix_migrations_migration_id", "migrations", "migration_id"),
        ("ix_migrations_user_id", "migrations", "user_id"),
        ("ix_migrations_plan_id", "migrations", "plan_id"),
        ("ix_migrations_active_identity", "migrations", "active_identity"),
        ("ix_migration_files_migration_id", "migration_files", "migration_id"),
        ("ix_reports_report_id", "reports", "report_id"),
        ("ix_reports_user_id", "reports", "user_id"),
        ("ix_reports_migration_id", "reports", "migration_id"),
        ("ix_reports_plan_id", "reports", "plan_id"),
        ("ix_audit_events_event", "audit_events", "event"),
        ("ix_audit_events_user_id", "audit_events", "user_id"),
        ("ix_audit_events_migration_id", "audit_events", "migration_id"),
        ("ix_audit_events_created_at", "audit_events", "created_at"),
    ):
        sa.Index(name, metadata.tables[table].c[column])
    return metadata


def upgrade():
    """Create missing tables, then safely supplement older database rows."""
    bind = op.get_bind()
    _baseline_metadata().create_all(bind=bind, checkfirst=True)
    upgrade_legacy_schema(bind)


def downgrade():
    """The baseline is intentionally forward-only to protect persisted data."""
    pass
