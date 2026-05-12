"""Event sourcing domain models."""

import uuid
from datetime import datetime
from enum import StrEnum, auto
from typing import Any

from pydantic import BaseModel, Field


class EventAggregateType(StrEnum):
    """Types of aggregates that can have events."""

    ACCOUNT = auto()
    PASSKEY = auto()
    QUOTE = auto()


class EventType(StrEnum):
    """Types of events that can occur."""

    # Account events
    ACCOUNT_CREATED = auto()
    ACCOUNT_SESSION_CREATED = auto()
    ACCOUNT_SESSION_ENDED = auto()

    # Passkey events
    PASSKEY_CHALLENGE_CREATED = auto()
    PASSKEY_CHALLENGE_CONSUMED = auto()
    PASSKEY_CREDENTIAL_REGISTERED = auto()
    PASSKEY_AUTHENTICATION_SUCCESS = auto()
    PASSKEY_AUTHENTICATION_FAILURE = auto()

    # Quote events
    QUOTE_CREATED = auto()
    QUOTE_SUBMITTED = auto()
    QUOTE_NEEDS_REVIEW = auto()
    QUOTE_REVIEW_STARTED = auto()
    QUOTE_QUOTED = auto()
    QUOTE_ACCEPTED = auto()
    QUOTE_DECLINED = auto()
    QUOTE_CLOSED = auto()
    QUOTE_LOCATION_ADDED = auto()
    QUOTE_ANSWERS_ADDED = auto()
    QUOTE_UPLOAD_DECLARED = auto()


class EventActorType(StrEnum):
    """Types of actors that can perform actions."""

    SYSTEM = auto()
    ACCOUNT = auto()
    OPERATOR = auto()
    ANONYMOUS = auto()


class Event(BaseModel):
    """Append-only event model."""

    event_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    aggregate_type: EventAggregateType
    aggregate_id: str
    event_type: EventType
    created_at: datetime = Field(default_factory=datetime.utcnow)
    actor_type: EventActorType | None = None
    actor_id: str | None = None
    redacted_summary: str = ""
    encrypted_payload: str | None = None  # Base64-encoded encrypted JSON

    class Config:
        frozen = True  # Events are immutable

    @classmethod
    def for_quote(
        cls,
        quote_id: str,
        event_type: EventType,
        actor_type: EventActorType | None = None,
        actor_id: str | None = None,
        redacted_summary: str = "",
        encrypted_payload: str | None = None,
    ) -> "Event":
        """Create an event for a quote aggregate."""
        return cls(
            aggregate_type=EventAggregateType.QUOTE,
            aggregate_id=quote_id,
            event_type=event_type,
            actor_type=actor_type,
            actor_id=actor_id,
            redacted_summary=redacted_summary,
            encrypted_payload=encrypted_payload,
        )

    @classmethod
    def for_account(
        cls,
        account_id: str,
        event_type: EventType,
        actor_type: EventActorType | None = None,
        actor_id: str | None = None,
        redacted_summary: str = "",
        encrypted_payload: str | None = None,
    ) -> "Event":
        """Create an event for an account aggregate."""
        return cls(
            aggregate_type=EventAggregateType.ACCOUNT,
            aggregate_id=account_id,
            event_type=event_type,
            actor_type=actor_type,
            actor_id=actor_id,
            redacted_summary=redacted_summary,
            encrypted_payload=encrypted_payload,
        )

    def to_dict_safe(self) -> dict[str, Any]:
        """Return a dictionary with only non-sensitive fields."""
        return {
            "event_id": self.event_id,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": self.aggregate_id,
            "event_type": self.event_type,
            "created_at": self.created_at.isoformat(),
            "actor_type": self.actor_type,
            "actor_id": self.actor_id,
            "redacted_summary": self.redacted_summary,
            # encrypted_payload is NOT exposed in safe views
        }
