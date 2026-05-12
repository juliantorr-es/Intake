"""Time utilities for Intake.

Provides timezone-aware UTC datetime helpers for consistent time handling.
All returned datetimes are timezone-aware UTC.
"""

from datetime import datetime, timedelta, timezone


UTC = timezone.utc


def utc_now() -> datetime:
    """Return current time as timezone-aware UTC datetime."""
    return datetime.now(UTC)


def utc_expires_in(seconds: int) -> datetime:
    """Return a timezone-aware UTC datetime that is `seconds` in the future."""
    return utc_now() + timedelta(seconds=seconds)


def utc_expired() -> datetime:
    """Return a timezone-aware UTC datetime in the past (expired)."""
    return utc_now() - timedelta(seconds=1)
