"""Event logging service for append-only audit events."""

from functools import lru_cache
from typing import Any

from intake.domain.events import Event, EventActorType, EventAggregateType, EventType
from intake.domain.quotes import Quote, QuoteStatus
from intake.storage.repositories import EventRepository


class EventLogService:
    """Service for logging append-only events.

    Events are:
    - Immutable once created
    - Always appended, never mutated
    - Have redacted summaries (no sensitive data)
    - May have encrypted payloads for sensitive details
    """

    def __init__(self, repository: EventRepository | None = None):
        """Initialize event log service.

        Args:
            repository: EventRepository instance. If None, creates default.
        """
        self._repo = repository or EventRepository()

    def append(self, event: Event) -> Event:
        """Append an event to the log.

        Args:
            event: Event to append

        Returns:
            The appended event (as returned by repository)
        """
        return self._repo.append(event)

    def append_quote_event(
        self,
        quote: Quote,
        event_type: EventType,
        actor_type: EventActorType | None = None,
        actor_id: str | None = None,
        redacted_summary: str = "",
        encrypted_payload: dict[str, Any] | None = None,
    ) -> Event:
        """Append an event for a quote.

        Args:
            quote: The quote aggregate
            event_type: Type of event
            actor_type: Type of actor (SYSTEM, ACCOUNT, OPERATOR, ANONYMOUS)
            actor_id: ID of the actor
            redacted_summary: Human-readable summary (redacted, no sensitive data)
            encrypted_payload: Optional encrypted payload with sensitive details

        Returns:
            The appended event
        """
        from intake.services.crypto_service import get_crypto_service

        encrypted_payload_str = None
        if encrypted_payload:
            crypto = get_crypto_service()
            encrypted = crypto.encrypt_json(encrypted_payload)
            encrypted_payload_str = encrypted.model_dump_json()

        event = Event.for_quote(
            quote_id=quote.id,
            event_type=event_type,
            actor_type=actor_type,
            actor_id=actor_id,
            redacted_summary=redacted_summary,
            encrypted_payload=encrypted_payload_str,
        )
        return self.append(event)

    def get_for_quote(self, quote_id: str) -> list[Event]:
        """Get all events for a quote.

        Args:
            quote_id: ID of the quote

        Returns:
            List of events for the quote
        """
        return self._repo.get_for_aggregate(
            EventAggregateType.QUOTE,
            quote_id,
        )

    def get_for_account(self, account_id: str) -> list[Event]:
        """Get all events for an account.

        Args:
            account_id: ID of the account

        Returns:
            List of events for the account
        """
        return self._repo.get_for_aggregate(
            EventAggregateType.ACCOUNT,
            account_id,
        )

    def log_quote_created(self, quote: Quote, actor_type: EventActorType, actor_id: str | None) -> Event:
        """Log that a quote was created."""
        return self.append_quote_event(
            quote=quote,
            event_type=EventType.QUOTE_CREATED,
            actor_type=actor_type,
            actor_id=actor_id,
            redacted_summary=f"Quote created for {quote.service_lane.value if quote.service_lane else 'unknown'}",
        )

    def log_quote_submitted(self, quote: Quote, actor_id: str) -> Event:
        """Log that a quote was submitted."""
        return self.append_quote_event(
            quote=quote,
            event_type=EventType.QUOTE_SUBMITTED,
            actor_type=EventActorType.ACCOUNT,
            actor_id=actor_id,
            redacted_summary="Quote submitted for review",
        )

    def log_quote_status_change(
        self,
        quote: Quote,
        new_status: QuoteStatus,
        actor_type: EventActorType,
        actor_id: str | None,
    ) -> Event:
        """Log a quote status change."""
        return self.append_quote_event(
            quote=quote,
            event_type=EventLogService._status_to_event_type(new_status),
            actor_type=actor_type,
            actor_id=actor_id,
            redacted_summary=f"Quote status changed to {new_status.value}",
        )

    @staticmethod
    def _status_to_event_type(status: QuoteStatus) -> EventType:
        """Map quote status to event type."""
        mapping = {
            QuoteStatus.NEEDS_REVIEW: EventType.QUOTE_NEEDS_REVIEW,
            QuoteStatus.REVIEWING: EventType.QUOTE_REVIEW_STARTED,
            QuoteStatus.QUOTED: EventType.QUOTE_QUOTED,
            QuoteStatus.ACCEPTED: EventType.QUOTE_ACCEPTED,
            QuoteStatus.DECLINED: EventType.QUOTE_DECLINED,
            QuoteStatus.CLOSED: EventType.QUOTE_CLOSED,
        }
        return mapping.get(status, EventType.QUOTE_SUBMITTED)


@lru_cache()
def get_event_log_service() -> EventLogService:
    """Get cached event log service instance."""
    return EventLogService()


def reset_event_log_service() -> None:
    """Reset the cached event log service (useful for testing)."""
    get_event_log_service.cache_clear()
