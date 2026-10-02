"""Add persisted execution-lease and cancellation fields.

Revision ID: 20260927_02
Revises: 20260927_01
Create Date: 2026-09-27
"""

from alembic import op
import sqlalchemy as sa


revision = "20260927_02"
down_revision = "20260927_01"
branch_labels = None
depends_on = None


def _column_names():
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns("migrations")}


def upgrade():
    """Add fields without dropping or rewriting existing migration records."""
    existing = _column_names()
    additions = (
        ("cancellation_requested", sa.Column("cancellation_requested", sa.Boolean(), nullable=False, server_default=sa.text("0"))),
        ("worker_token", sa.Column("worker_token", sa.String(length=64), nullable=True)),
        ("lease_expires_at", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True)),
        ("last_heartbeat_at", sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True)),
        ("retry_count", sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("0"))),
        ("updated_at", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True)),
    )
    for name, column in additions:
        if name not in existing:
            op.add_column("migrations", column)
    inspector = sa.inspect(op.get_bind())
    indexes = {item["name"] for item in inspector.get_indexes("migrations")}
    if "ix_migrations_worker_token" not in indexes:
        op.create_index("ix_migrations_worker_token", "migrations", ["worker_token"])
    if "ix_migrations_lease_expires_at" not in indexes:
        op.create_index("ix_migrations_lease_expires_at", "migrations", ["lease_expires_at"])


def downgrade():
    """Forward-only project policy: do not destructively remove persisted data."""
    pass
