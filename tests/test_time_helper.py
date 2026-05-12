"""Tests for time helper utilities."""

from datetime import datetime, timedelta, timezone

from intake.domain.time import UTC, utc_expired, utc_expires_in, utc_now


def test_utc_now_returns_aware_datetime():
    """utc_now returns timezone-aware UTC datetime."""
    now = utc_now()
    assert now.tzinfo is not None
    assert now.tzinfo == UTC
    assert now.tzinfo == timezone.utc


def test_utc_expires_in_returns_aware_datetime():
    """utc_expires_in returns timezone-aware UTC datetime in the future."""
    now = utc_now()
    expiry = utc_expires_in(60)
    assert expiry.tzinfo is not None
    assert expiry.tzinfo == UTC
    assert expiry > now
    assert (expiry - now).total_seconds() >= 59  # Allow small timing variance


def test_utc_expired_returns_aware_datetime_in_past():
    """utc_expired returns timezone-aware UTC datetime in the past."""
    now = utc_now()
    expired = utc_expired()
    assert expired.tzinfo is not None
    assert expired.tzinfo == UTC
    assert expired < now


def test_utc_now_consistency():
    """Multiple calls to utc_now return consistent timezone-aware datetimes."""
    now1 = utc_now()
    now2 = utc_now()
    assert now1.tzinfo == now2.tzinfo == UTC
    # They should be very close (within a second for fast successive calls)
    assert abs((now2 - now1).total_seconds()) < 2


def test_utc_expires_in_various_intervals():
    """utc_expires_in works with various time intervals."""
    now = utc_now()
    
    # Test seconds
    expiry_10s = utc_expires_in(10)
    assert (expiry_10s - now).total_seconds() >= 9
    assert (expiry_10s - now).total_seconds() <= 11
    
    # Test minutes
    expiry_5min = utc_expires_in(5 * 60)
    assert (expiry_5min - now).total_seconds() >= 5 * 60 - 1
    assert (expiry_5min - now).total_seconds() <= 5 * 60 + 1
    
    # Test hours
    expiry_1h = utc_expires_in(3600)
    assert (expiry_1h - now).total_seconds() >= 3599
    assert (expiry_1h - now).total_seconds() <= 3601


def test_utc_constant_is_utc():
    """UTC constant is timezone.utc."""
    assert UTC == timezone.utc
