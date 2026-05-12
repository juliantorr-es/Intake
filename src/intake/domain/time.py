"""Time utilities for Intake.

Provides timezone-aware UTC datetime helpers for consistent time handling.
All returned datetimes are timezone-aware UTC.

SQLite/SQLModel note: Datetime values stored in SQLite may round-trip as naive
(even if written as aware). Always normalize with as_aware_utc() before comparison.
"""

from datetime import datetime, timedelta, timezone


UTC = timezone.utc


def utc_now() -> datetime:
    """Return current time as timezone-aware UTC datetime."""
    return datetime.now(UTC)


def as_aware_utc(value: datetime) -> datetime:
    """Normalize a datetime to timezone-aware UTC.
    
    Treats naive datetimes as UTC (common from SQLite/SQLModel round-trips).
    Converts aware datetimes to UTC timezone.
    
    Args:
        value: A datetime that may be naive or aware
        
    Returns:
        Timezone-aware UTC datetime
    """
    if value.tzinfo is None or value.utcoffset() is None:
        # Naive datetime - assume UTC
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def utc_is_after(left: datetime, right: datetime) -> bool:
    """Compare two datetimes in UTC, normalizing both to aware first."""
    return as_aware_utc(left) > as_aware_utc(right)


def utc_is_before(left: datetime, right: datetime) -> bool:
    """Compare two datetimes in UTC, normalizing both to aware first."""
    return as_aware_utc(left) < as_aware_utc(right)


def utc_is_expired(expires_at: datetime) -> bool:
    """Check if a datetime has expired (is in the past relative to UTC now)."""
    return utc_is_after(utc_now(), expires_at)


def utc_expires_in(seconds: int) -> datetime:
    """Return a timezone-aware UTC datetime that is `seconds` in the future."""
    return utc_now() + timedelta(seconds=seconds)


def utc_expired() -> datetime:
    """Return a timezone-aware UTC datetime in the past (expired)."""
    return utc_now() - timedelta(seconds=1)
