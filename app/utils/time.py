"""Timezone-aware timestamp helpers for application-owned persistence."""

from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


def utc_now():
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    """Store UTC timestamps and restore legacy SQLite values as aware UTC.

    SQLite has no native timezone-aware datetime type. Existing application
    timestamps were UTC-naive, so legacy values are interpreted as UTC rather
    than being shifted during the versioned upgrade.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
