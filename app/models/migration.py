from app.extensions import db
from app.utils.time import UTCDateTime, utc_now


class MigrationPlan(db.Model):
    """Owner-scoped, persisted assessment plan; it never stores credentials."""

    __tablename__ = "migration_plans"

    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    source_cloud = db.Column(db.String(20), nullable=False)
    target_cloud = db.Column(db.String(20), nullable=False)
    source_session_reference = db.Column(db.String(128), nullable=True)
    target_session_reference = db.Column(db.String(128), nullable=True)
    status = db.Column(db.String(40), nullable=False, default="generated")
    resource_count = db.Column(db.Integer, nullable=False, default=0)
    execution_ready_count = db.Column(db.Integer, nullable=False, default=0)
    planning_review_count = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(UTCDateTime(), nullable=False, default=utc_now)
    updated_at = db.Column(UTCDateTime(), nullable=False, default=utc_now, onupdate=utc_now)

    resources = db.relationship(
        "MigrationPlanResource", backref="plan", lazy=True, cascade="all, delete-orphan"
    )


class MigrationPlanResource(db.Model):
    """Safe, resource-level migration assessment belonging to a plan."""

    __tablename__ = "migration_plan_resources"

    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey("migration_plans.id"), nullable=False, index=True)
    source_cloud = db.Column(db.String(20), nullable=False)
    target_cloud = db.Column(db.String(20), nullable=False)
    service = db.Column(db.String(80), nullable=False)
    resource_id = db.Column(db.String(1024), nullable=False)
    resource_name = db.Column(db.String(1024), nullable=False)
    target_service = db.Column(db.String(160), nullable=False)
    capability_classification = db.Column(db.String(32), nullable=False)
    compatibility = db.Column(db.Integer, nullable=False, default=0)
    execution_mode = db.Column(db.String(64), nullable=False)
    status = db.Column(db.String(160), nullable=False)
    risk_level = db.Column(db.String(20), nullable=False, default="medium")
    dependencies = db.Column(db.Text, nullable=False, default="[]")
    preflight_findings = db.Column(db.Text, nullable=False, default="[]")
    manual_review_reasons = db.Column(db.Text, nullable=False, default="[]")
    recommendation_data = db.Column(db.Text, nullable=False, default="{}")
    source_metadata = db.Column(db.Text, nullable=False, default="{}")
    created_at = db.Column(UTCDateTime(), nullable=False, default=utc_now)
    updated_at = db.Column(UTCDateTime(), nullable=False, default=utc_now, onupdate=utc_now)

class Migration(db.Model):

    __tablename__ = "migrations"


    id = db.Column(
        db.Integer,
        primary_key=True
    )


    migration_id = db.Column(
        db.String(64),
        unique=True,
        nullable=False,
        index=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id"
        ),
        nullable=True,
        index=True
    )

    plan_id = db.Column(db.Integer, db.ForeignKey("migration_plans.id"), nullable=True, index=True)

    active_identity = db.Column(db.String(64), nullable=True, unique=True, index=True)

    source_cloud = db.Column(
        db.String(20),
        nullable=False
    )

    target_cloud = db.Column(
        db.String(20),
        nullable=False
    )

    resource_type = db.Column(
        db.String(50),
        nullable=False
    )

    resource_name = db.Column(
        db.String(255),
        nullable=False
    )

    status = db.Column(
        db.String(30),
        nullable=False,
        default="pending"
    )

    total_files = db.Column(
        db.Integer,
        default=0,
        nullable=False
    )

    uploaded_files = db.Column(
        db.Integer,
        default=0,
        nullable=False
    )

    failed_files = db.Column(
        db.Integer,
        default=0,
        nullable=False
    )

    total_size_bytes = db.Column(
        db.BigInteger,
        default=0,
        nullable=False
    )

    transferred_bytes = db.Column(
        db.BigInteger,
        default=0,
        nullable=False
    )

    total_batches = db.Column(
        db.Integer,
        default=0,
        nullable=False
    )

    destination_resource_group = db.Column(db.String(255), nullable=True)
    destination_storage_account = db.Column(db.String(64), nullable=True)
    destination_container = db.Column(db.String(63), nullable=True)
    target_region = db.Column(db.String(64), nullable=True)
    destination_provisioning_mode = db.Column(db.String(32), nullable=True)
    execution_configuration = db.Column(db.Text, nullable=False, default="{}")
    failure_reason = db.Column(db.String(255), nullable=True)
    uncertain_external_operation = db.Column(db.Boolean, nullable=False, default=False)
    cancellation_requested = db.Column(db.Boolean, nullable=False, default=False)
    worker_token = db.Column(db.String(64), nullable=True, index=True)
    lease_expires_at = db.Column(UTCDateTime(), nullable=True, index=True)
    last_heartbeat_at = db.Column(UTCDateTime(), nullable=True)
    retry_count = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(UTCDateTime(), nullable=False, default=utc_now, onupdate=utc_now)

    started_at = db.Column(
        UTCDateTime(),
        default=utc_now,
        nullable=True
    )

    completed_at = db.Column(
        UTCDateTime(),
        nullable=True
    )

    created_at = db.Column(
        UTCDateTime(),
        default=utc_now,
        nullable=False
    )

    files = db.relationship(
        "MigrationFile",
        backref="migration",
        lazy=True,
        cascade="all, delete-orphan"
    )

    plan = db.relationship("MigrationPlan", backref="executions", foreign_keys=[plan_id])
    reports = db.relationship("Report", backref="migration", lazy=True, cascade="all, delete-orphan")

    def __repr__(self):

        return (
            f"<Migration "
            f"{self.migration_id} "
            f"{self.status}>"
        )

class MigrationFile(db.Model):

    __tablename__ = "migration_files"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    migration_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "migrations.id"
        ),
        nullable=False,
        index=True
    )

    object_key = db.Column(
        db.String(1024),
        nullable=False
    )

    __table_args__ = (
        db.UniqueConstraint("migration_id", "object_key", name="uq_migration_file_object"),
    )

    size_bytes = db.Column(
        db.BigInteger,
        default=0,
        nullable=False
    )

    batch_number = db.Column(
        db.Integer,
        default=1,
        nullable=False
    )

    status = db.Column(
        db.String(30),
        nullable=False,
        default="pending"
    )

    error_message = db.Column(
        db.Text,
        nullable=True
    )

    source_etag = db.Column(db.String(256), nullable=True)
    destination_etag = db.Column(db.String(256), nullable=True)
    verification_status = db.Column(db.String(40), nullable=True)
    attempt_count = db.Column(db.Integer, default=0, nullable=False)
    last_attempt_at = db.Column(UTCDateTime(), nullable=True)
    bytes_transferred = db.Column(db.BigInteger, default=0, nullable=False)

    started_at = db.Column(
        UTCDateTime(),
        nullable=True
    )

    completed_at = db.Column(
        UTCDateTime(),
        nullable=True
    )

    created_at = db.Column(
        UTCDateTime(),
        default=utc_now,
        nullable=False
    )

    def __repr__(self):

        return (
            f"<MigrationFile "
            f"{self.object_key} "
            f"{self.status}>"
        )
