"""Persisted, owner-scoped migration report snapshots."""

from app.extensions import db
from app.utils.time import UTCDateTime, utc_now


class Report(db.Model):
    """A safe report snapshot derived only from persisted migration state."""

    __tablename__ = "reports"

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.String(64), nullable=False, unique=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    migration_id = db.Column(db.Integer, db.ForeignKey("migrations.id"), nullable=False, unique=True, index=True)
    plan_id = db.Column(db.Integer, db.ForeignKey("migration_plans.id"), nullable=True, index=True)
    status = db.Column(db.String(40), nullable=False)
    report_data = db.Column(db.Text, nullable=False, default="{}")
    generated_at = db.Column(UTCDateTime(), nullable=False, default=utc_now, onupdate=utc_now)

    plan = db.relationship("MigrationPlan", backref="reports", foreign_keys=[plan_id])
