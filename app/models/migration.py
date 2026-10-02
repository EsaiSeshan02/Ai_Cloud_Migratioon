"""
==========================================================
AI CLOUD MIGRATION
MIGRATION DATABASE MODELS
==========================================================

Stores:

    - Migration-level information
    - Individual migrated files
    - Migration progress
    - Migration status
    - Failed file information

These models will later be used for:

    - Resume support
    - Retry failed files
    - Migration history
    - Progress tracking
    - Migration reports
"""


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


# ==========================================================
# MIGRATION MODEL
# ==========================================================

class Migration(db.Model):

    __tablename__ = "migrations"

    # ------------------------------------------------------
    # PRIMARY KEY
    # ------------------------------------------------------

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    # ------------------------------------------------------
    # MIGRATION IDENTIFIER
    # ------------------------------------------------------

    migration_id = db.Column(
        db.String(64),
        unique=True,
        nullable=False,
        index=True
    )

    # ------------------------------------------------------
    # USER
    # ------------------------------------------------------

    user_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id"
        ),
        nullable=True,
        index=True
    )

    # Optional for historical rows created before owner-scoped execution was
    # introduced. New executions always supply an owner.
    plan_id = db.Column(db.Integer, db.ForeignKey("migration_plans.id"), nullable=True, index=True)

    # Set only while a migration is active. The database unique index protects
    # against duplicate starts across web workers without changing old rows.
    active_identity = db.Column(db.String(64), nullable=True, unique=True, index=True)

    # ------------------------------------------------------
    # SOURCE / TARGET
    # ------------------------------------------------------

    source_cloud = db.Column(
        db.String(20),
        nullable=False
    )

    target_cloud = db.Column(
        db.String(20),
        nullable=False
    )

    # ------------------------------------------------------
    # RESOURCE INFORMATION
    # ------------------------------------------------------

    resource_type = db.Column(
        db.String(50),
        nullable=False
    )

    resource_name = db.Column(
        db.String(255),
        nullable=False
    )

    # ------------------------------------------------------
    # MIGRATION STATUS
    # ------------------------------------------------------

    status = db.Column(
        db.String(30),
        nullable=False,
        default="pending"
    )

    # ------------------------------------------------------
    # FILE COUNTERS
    # ------------------------------------------------------

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

    # ------------------------------------------------------
    # DATA SIZE
    # ------------------------------------------------------

    total_size_bytes = db.Column(
        db.BigInteger,
        default=0,
        nullable=False
    )

    # Completed transfer bytes only.  Bytes for a Blob merely found during a
    # resume are deliberately not counted as newly transferred.
    transferred_bytes = db.Column(
        db.BigInteger,
        default=0,
        nullable=False
    )

    # ------------------------------------------------------
    # BATCH INFORMATION
    # ------------------------------------------------------

    total_batches = db.Column(
        db.Integer,
        default=0,
        nullable=False
    )

    # Destination details are persisted so an interrupted S3 migration can be
    # resumed after the web process restarts.  They intentionally contain no
    # credentials; Azure keys are retrieved again from an authenticated target
    # session when a user resumes work.
    destination_resource_group = db.Column(db.String(255), nullable=True)
    destination_storage_account = db.Column(db.String(64), nullable=True)
    destination_container = db.Column(db.String(63), nullable=True)
    target_region = db.Column(db.String(64), nullable=True)
    destination_provisioning_mode = db.Column(db.String(32), nullable=True)
    execution_configuration = db.Column(db.Text, nullable=False, default="{}")
    # Only short, application-defined failure categories are stored here.
    # Provider diagnostics and credentials must never be persisted.
    failure_reason = db.Column(db.String(255), nullable=True)

    # A synchronous Lambda/Kudu call can outlive this process.  When its
    # outcome is unknown, retain the logical identity as a durable blocker
    # until an owner explicitly confirms the target was inspected.
    uncertain_external_operation = db.Column(db.Boolean, nullable=False, default=False)

    # Persisted worker lifecycle. Credentials remain in the short-lived cloud
    # session only; these fields describe ownership of local execution work.
    cancellation_requested = db.Column(db.Boolean, nullable=False, default=False)
    worker_token = db.Column(db.String(64), nullable=True, index=True)
    lease_expires_at = db.Column(UTCDateTime(), nullable=True, index=True)
    last_heartbeat_at = db.Column(UTCDateTime(), nullable=True)
    retry_count = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(UTCDateTime(), nullable=False, default=utc_now, onupdate=utc_now)

    # ------------------------------------------------------
    # TIMESTAMPS
    # ------------------------------------------------------

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

    # ------------------------------------------------------
    # RELATIONSHIP
    # ------------------------------------------------------

    files = db.relationship(
        "MigrationFile",
        backref="migration",
        lazy=True,
        cascade="all, delete-orphan"
    )

    plan = db.relationship("MigrationPlan", backref="executions", foreign_keys=[plan_id])
    reports = db.relationship("Report", backref="migration", lazy=True, cascade="all, delete-orphan")

    # ------------------------------------------------------
    # REPRESENTATION
    # ------------------------------------------------------

    def __repr__(self):

        return (
            f"<Migration "
            f"{self.migration_id} "
            f"{self.status}>"
        )


# ==========================================================
# MIGRATION FILE MODEL
# ==========================================================

class MigrationFile(db.Model):

    __tablename__ = "migration_files"

    # ------------------------------------------------------
    # PRIMARY KEY
    # ------------------------------------------------------

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    # ------------------------------------------------------
    # MIGRATION RELATIONSHIP
    # ------------------------------------------------------

    migration_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "migrations.id"
        ),
        nullable=False,
        index=True
    )

    # ------------------------------------------------------
    # OBJECT / FILE INFORMATION
    # ------------------------------------------------------

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

    # ------------------------------------------------------
    # BATCH
    # ------------------------------------------------------

    batch_number = db.Column(
        db.Integer,
        default=1,
        nullable=False
    )

    # ------------------------------------------------------
    # FILE STATUS
    # ------------------------------------------------------

    status = db.Column(
        db.String(30),
        nullable=False,
        default="pending"
    )

    # ------------------------------------------------------
    # ERROR INFORMATION
    # ------------------------------------------------------

    error_message = db.Column(
        db.Text,
        nullable=True
    )

    # Provider ETags are retained as operational metadata only.  An S3 ETag
    # is not always an MD5 checksum (for example multipart uploads), so the
    # transfer service never treats matching ETags across providers as proof
    # of content equality.
    source_etag = db.Column(db.String(256), nullable=True)
    destination_etag = db.Column(db.String(256), nullable=True)
    verification_status = db.Column(db.String(40), nullable=True)
    attempt_count = db.Column(db.Integer, default=0, nullable=False)
    last_attempt_at = db.Column(UTCDateTime(), nullable=True)
    bytes_transferred = db.Column(db.BigInteger, default=0, nullable=False)

    # ------------------------------------------------------
    # TIMESTAMPS
    # ------------------------------------------------------

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

    # ------------------------------------------------------
    # REPRESENTATION
    # ------------------------------------------------------

    def __repr__(self):

        return (
            f"<MigrationFile "
            f"{self.object_key} "
            f"{self.status}>"
        )
