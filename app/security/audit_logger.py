"""Audit-log facade for sensitive operations without credential data."""

from datetime import datetime

from flask import current_app

from app.extensions import db
from app.security.logging_utils import log_event


class AuditEvent(db.Model):
    """Minimal durable audit trail; fields are intentionally allow-listed."""

    __tablename__ = "audit_events"

    id = db.Column(db.Integer, primary_key=True)
    event = db.Column(db.String(96), nullable=False, index=True)
    user_id = db.Column(db.Integer, nullable=True, index=True)
    migration_id = db.Column(db.String(64), nullable=True, index=True)
    status = db.Column(db.String(48), nullable=True)
    category = db.Column(db.String(48), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)


def audit_event(event, *, user_id=None, migration_id=None, operation=None, status=None, category=None):
    log_event(
        current_app.logger,
        event,
        user_id=user_id,
        migration_id=migration_id,
        operation=operation,
        status=status,
        category=category,
    )
    try:
        db.session.add(AuditEvent(
            event=str(event)[:96], user_id=user_id, migration_id=str(migration_id)[:64] if migration_id else None,
            status=str(status)[:48] if status else None, category=str(category)[:48] if category else None,
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.warning("audit_event_persistence_failed operation=audit category=database")
