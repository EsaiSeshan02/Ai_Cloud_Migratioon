from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import or_, select, update

from app.extensions import db
from app.models.migration import Migration
from app.utils.time import utc_now


LEASE_SECONDS = 300
ACTIVE_STATUSES = {"queued", "preparing", "running", "deploying", "validating", "cancelling"}
TERMINAL_STATUSES = {
    "completed", "completed_with_failures", "completed_with_review", "failed",
    "cancelled", "manual_review_required",
}


def new_worker_token():
    return uuid.uuid4().hex


def claim_migration(migration_id, worker_token=None, allowed_statuses=None, reclaim_expired=True, lease_seconds=LEASE_SECONDS):
    """Atomically claim a non-terminal execution, returning its token or ``None``.

    SQLite serializes writers, so its lease behaviour is appropriate for the
    single-process prototype.  A future distributed worker can reuse this
    conditional update with a database that offers stronger row locking.
    """
    token = worker_token or new_worker_token()
    now = utc_now()
    statuses = set(allowed_statuses or ACTIVE_STATUSES | {"interrupted"})
    ownership = or_(
        Migration.worker_token.is_(None),
        Migration.lease_expires_at.is_(None),
        Migration.lease_expires_at < now,
    ) if reclaim_expired else Migration.worker_token.is_(None)
    statement = (
        update(Migration)
        .where(
            Migration.migration_id == migration_id,
            Migration.status.in_(statuses),
            Migration.cancellation_requested.is_(False),
            ownership,
        )
        .values(worker_token=token, lease_expires_at=now + timedelta(seconds=lease_seconds), last_heartbeat_at=now)
    )
    result = db.session.execute(statement)
    db.session.commit()
    return token if result.rowcount == 1 else None


def renew_claim(migration_id, worker_token, lease_seconds=LEASE_SECONDS):
    """Keep a worker lease alive only while it still owns the migration."""
    if not worker_token:
        return False
    now = utc_now()
    result = db.session.execute(
        update(Migration)
        .where(
            Migration.migration_id == migration_id,
            Migration.worker_token == worker_token,
            Migration.lease_expires_at > now,
        )
        .values(lease_expires_at=now + timedelta(seconds=lease_seconds), last_heartbeat_at=now)
        .execution_options(synchronize_session=False)
    )
    db.session.commit()
    return result.rowcount == 1


def commit_worker_changes(migration_id, worker_token):
    """Commit pending ORM changes only if this token still owns the row.

    The conditional heartbeat update and ORM flush share one transaction. If
    the token has been cleared or replaced, pending changes are rolled back
    before they can overwrite the current worker's state.
    """
    if not worker_token:
        db.session.rollback()
        return False
    with db.session.no_autoflush:
        result = db.session.execute(
            update(Migration)
            .where(Migration.migration_id == migration_id, Migration.worker_token == worker_token)
            .values(last_heartbeat_at=utc_now())
            .execution_options(synchronize_session=False)
        )
    if result.rowcount != 1:
        db.session.rollback()
        return False
    db.session.flush()
    db.session.commit()
    return True


def commit_unclaimed_changes(migration_id):
    """Commit user/recovery changes only while the persisted claim is absent."""
    with db.session.no_autoflush:
        result = db.session.execute(
            update(Migration)
            .where(Migration.migration_id == migration_id, Migration.worker_token.is_(None))
            .values(last_heartbeat_at=utc_now())
        )
    if result.rowcount != 1:
        db.session.rollback()
        return False
    db.session.flush()
    db.session.commit()
    return True


def cancellation_requested(migration_id):
    """Read persisted cancellation intent without relying on a stale ORM object."""
    migration = db.session.execute(
        select(Migration.cancellation_requested).where(Migration.migration_id == migration_id)
    ).scalar_one_or_none()
    return bool(migration)


def release_claim(migration, worker_token=None):
    """Atomically clear a claim only when the persisted token matches exactly."""
    if not worker_token:
        return False
    result = db.session.execute(
        update(Migration)
        .where(Migration.id == migration.id, Migration.worker_token == worker_token)
        .values(worker_token=None, lease_expires_at=None, last_heartbeat_at=utc_now())
        .execution_options(synchronize_session=False)
    )
    db.session.commit()
    return result.rowcount == 1


def request_cancellation(migration):
    """Persist a cooperative cancellation request for an active migration."""
    if migration.status in TERMINAL_STATUSES:
        return False
    migration.cancellation_requested = True
    if migration.worker_token is None and migration.status in {"queued", "preparing", "interrupted", "failed", "completed_with_failures"}:
        return finalize_cancelled(migration)
    if migration.status not in {"cancelling", "cancelled"}:
        migration.status = "cancelling"
    db.session.commit()
    return True


def finalize_cancelled(migration, worker_token=None):
    """Record a cancellation outcome; no rollback is claimed or attempted."""
    migration.status = "cancelled"
    migration.completed_at = utc_now()
    migration.active_identity = None
    migration.failure_reason = "Migration was cancelled by its owner."
    migration.worker_token = None
    migration.lease_expires_at = None
    if worker_token is None:
        if migration.worker_token is not None:
            db.session.rollback()
            return False
        migration.worker_token = None
        migration.lease_expires_at = None
        if not commit_unclaimed_changes(migration.migration_id):
            return False
    elif not commit_worker_changes(migration.migration_id, worker_token):
        return False
    from app.services.report_service import generate_report_safely
    generate_report_safely(migration)
    return True


def mark_stale_executions_for_recovery():
    return Migration.query.filter(Migration.status.in_(ACTIVE_STATUSES)).all()
