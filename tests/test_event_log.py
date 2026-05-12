"""Tests for event logging."""

import pytest

from intake.domain.events import (
    Event,
    EventActorType,
    EventAggregateType,
    EventType,
)
from intake.domain.quotes import Quote, QuoteStatus, QuoteServiceLane
from intake.services.event_log import EventLogService, reset_event_log_service


@pytest.fixture(autouse=True)
def reset_event_log():
    """Reset event log service before and after tests."""
    reset_event_log_service()
    yield
    reset_event_log_service()


def test_event_creation():
    """Test event creation."""
    event = Event(
        aggregate_type=EventAggregateType.QUOTE,
        aggregate_id="quote-123",
        event_type=EventType.QUOTE_CREATED,
        actor_type=EventActorType.ACCOUNT,
        actor_id="account-456",
        redacted_summary="Quote created",
    )

    assert event.aggregate_type == EventAggregateType.QUOTE
    assert event.aggregate_id == "quote-123"
    assert event.event_type == EventType.QUOTE_CREATED
    assert event.actor_type == EventActorType.ACCOUNT
    assert event.actor_id == "account-456"
    assert event.redacted_summary == "Quote created"
    assert event.encrypted_payload is None


def test_event_for_quote():
    """Test Event.for_quote factory method."""
    event = Event.for_quote(
        quote_id="quote-123",
        event_type=EventType.QUOTE_CREATED,
        actor_type=EventActorType.ANONYMOUS,
        redacted_summary="Test quote created",
    )

    assert event.aggregate_type == EventAggregateType.QUOTE
    assert event.aggregate_id == "quote-123"
    assert event.event_type == EventType.QUOTE_CREATED
    assert event.actor_type == EventActorType.ANONYMOUS
    assert event.actor_id is None
    assert event.redacted_summary == "Test quote created"


def test_event_for_account():
    """Test Event.for_account factory method."""
    event = Event.for_account(
        account_id="account-123",
        event_type=EventType.ACCOUNT_CREATED,
        actor_type=EventActorType.SYSTEM,
        actor_id="system",
        redacted_summary="Account created",
    )

    assert event.aggregate_type == EventAggregateType.ACCOUNT
    assert event.aggregate_id == "account-123"
    assert event.event_type == EventType.ACCOUNT_CREATED


def test_event_immutable():
    """Test that events are immutable (frozen)."""
    event = Event(
        aggregate_type=EventAggregateType.QUOTE,
        aggregate_id="quote-123",
        event_type=EventType.QUOTE_CREATED,
    )

    with pytest.raises(Exception):  # Pydantic v2 raises ValidationError for frozen instances
        event.aggregate_id = "different-id"


def test_event_to_dict_safe():
    """Test that to_dict_safe excludes sensitive data."""
    event = Event(
        aggregate_type=EventAggregateType.QUOTE,
        aggregate_id="quote-123",
        event_type=EventType.QUOTE_CREATED,
        actor_type=EventActorType.ACCOUNT,
        actor_id="account-456",
        redacted_summary="Quote created",
        encrypted_payload='{"ciphertext": "...", "nonce": "..."}',
    )

    safe_dict = event.to_dict_safe()

    assert safe_dict["aggregate_id"] == "quote-123"
    assert safe_dict["event_type"] == EventType.QUOTE_CREATED
    assert safe_dict["redacted_summary"] == "Quote created"

    # encrypted_payload should NOT be in the safe dict
    assert "encrypted_payload" not in safe_dict


def test_event_aggregate_types():
    """Test all aggregate types."""
    assert EventAggregateType.ACCOUNT.value == "account"
    assert EventAggregateType.PASSKEY.value == "passkey"
    assert EventAggregateType.QUOTE.value == "quote"


def test_event_actor_types():
    """Test all actor types."""
    assert EventActorType.SYSTEM.value == "system"
    assert EventActorType.ACCOUNT.value == "account"
    assert EventActorType.OPERATOR.value == "operator"
    assert EventActorType.ANONYMOUS.value == "anonymous"


def test_quote_located_events():
    """Test quote-related event types."""
    quote_events = [
        EventType.QUOTE_CREATED,
        EventType.QUOTE_SUBMITTED,
        EventType.QUOTE_NEEDS_REVIEW,
        EventType.QUOTE_REVIEW_STARTED,
        EventType.QUOTE_QUOTED,
        EventType.QUOTE_ACCEPTED,
        EventType.QUOTE_DECLINED,
        EventType.QUOTE_CLOSED,
        EventType.QUOTE_LOCATION_ADDED,
        EventType.QUOTE_ANSWERS_ADDED,
        EventType.QUOTE_UPLOAD_DECLARED,
    ]
    for event_type in quote_events:
        assert event_type.value.startswith("quote_")


def test_account_events():
    """Test account-related event types."""
    account_events = [
        EventType.ACCOUNT_CREATED,
        EventType.ACCOUNT_SESSION_CREATED,
        EventType.ACCOUNT_SESSION_ENDED,
    ]
    for event_type in account_events:
        assert event_type.value.startswith("account_")


# Note: Full event logging service tests would require database setup
# which is beyond the scope of this bootstrap. These tests verify
# the domain model boundaries.
