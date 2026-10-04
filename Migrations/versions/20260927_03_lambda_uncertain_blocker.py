from alembic import op
import sqlalchemy as sa


revision = "20260927_03"
down_revision = "20260927_02"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("migrations")}
    if "uncertain_external_operation" not in columns:
        op.add_column(
            "migrations",
            sa.Column(
                "uncertain_external_operation",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )


def downgrade():
    pass
