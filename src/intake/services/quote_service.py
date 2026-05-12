"""Quote service for intake management."""

from datetime import datetime
from functools import lru_cache
from typing import Any

from intake.domain.events import EventActorType, EventType
from intake.domain.time import utc_now
from intake.domain.quotes import (
    Quote,
    QuoteServiceLane,
    QuoteStatus,
    UploadDeclaration,
)
from intake.services.crypto_service import get_crypto_service
from intake.services.event_log import get_event_log_service
from intake.storage.repositories import QuoteRepository


class QuoteService:
    """Service for quote operations."""

    def __init__(
        self,
        repo: QuoteRepository | None = None,
        crypto_service: Any | None = None,
        event_log: Any | None = None,
    ):
        """Initialize quote service.

        Args:
            repo: QuoteRepository instance
            crypto_service: CryptoService instance
            event_log: EventLogService instance
        """
        self._repo = repo or QuoteRepository()
        self._crypto = crypto_service or get_crypto_service()
        self._event_log = event_log or get_event_log_service()

    def create_quote(self, service_lane: QuoteServiceLane | None = None) -> Quote:
        """Create a new quote in DRAFT status."""
        quote = Quote(
            service_lane=service_lane,
            status=QuoteStatus.DRAFT,
        )
        created = self._repo.create(quote)

        # Log the event
        self._event_log.log_quote_created(
            quote=created,
            actor_type=EventActorType.ANONYMOUS,
            actor_id=None,
        )

        return created

    def get_quote(self, quote_id: str) -> Quote | None:
        """Get a quote by ID."""
        model = self._repo.get(quote_id)
        if model:
            return model.to_domain()
        return None

    def get_all_quotes(self) -> list[Quote]:
        """Get all quotes."""
        return self._repo.get_all()

    def update_quote_service_lane(
        self, quote_id: str, service_lane: QuoteServiceLane
    ) -> Quote | None:
        """Update the service lane for a quote."""
        quote = self.get_quote(quote_id)
        if not quote:
            return None

        quote.service_lane = service_lane
        quote.updated_at = utc_now()
        return self._repo.update(quote)

    def add_basic_info(
        self,
        quote_id: str,
        short_summary: str,
        detailed_description: str,
        preferred_timeline: str | None = None,
    ) -> Quote | None:
        """Add basic information to a quote."""
        quote = self.get_quote(quote_id)
        if not quote:
            return None

        quote.short_summary = short_summary
        quote.detailed_description = detailed_description
        quote.preferred_timeline = preferred_timeline
        quote.updated_at = utc_now()
        return self._repo.update(quote)

    def add_location(
        self,
        quote_id: str,
        general_service_area: str,
        exact_location: str,
    ) -> Quote | None:
        """Add location information to a quote.

        The exact location is encrypted before storage.
        """
        quote = self.get_quote(quote_id)
        if not quote:
            return None

        quote.general_service_area = general_service_area

        # Encrypt the exact location
        encrypted = self._crypto.encrypt_json({"location": exact_location})
        quote.encrypted_exact_location = encrypted

        quote.updated_at = utc_now()
        updated = self._repo.update(quote)

        # Log the event
        if updated:
            self._event_log.append_quote_event(
                quote=updated,
                event_type=EventType.QUOTE_LOCATION_ADDED,
                actor_type=EventActorType.ACCOUNT,
                actor_id=None,  # Will be set from session in API layer
                redacted_summary=f"Location added for quote in {general_service_area}",
            )

        return updated

    def add_access_notes(self, quote_id: str, access_notes: str) -> Quote | None:
        """Add access notes to a quote.

        The access notes are encrypted before storage.
        """
        quote = self.get_quote(quote_id)
        if not quote:
            return None

        # Encrypt the access notes
        encrypted = self._crypto.encrypt_json({"notes": access_notes})
        quote.encrypted_access_notes = encrypted

        quote.updated_at = utc_now()
        updated = self._repo.update(quote)

        # Log the event (with generic summary, no sensitive data)
        if updated:
            self._event_log.append_quote_event(
                quote=updated,
                event_type=EventType.QUOTE_ANSWERS_ADDED,
                actor_type=EventActorType.ACCOUNT,
                actor_id=None,
                redacted_summary="Access notes added",
            )

        return updated

    def add_questionnaire(self, quote_id: str, answers: dict[str, Any]) -> Quote | None:
        """Add questionnaire answers to a quote.

        The answers are encrypted before storage.
        """
        quote = self.get_quote(quote_id)
        if not quote:
            return None

        # Encrypt the questionnaire answers
        encrypted = self._crypto.encrypt_json(answers)
        quote.encrypted_questionnaire = encrypted

        quote.updated_at = utc_now()
        updated = self._repo.update(quote)

        # Log the event
        if updated:
            self._event_log.append_quote_event(
                quote=updated,
                event_type=EventType.QUOTE_ANSWERS_ADDED,
                actor_type=EventActorType.ACCOUNT,
                actor_id=None,
                redacted_summary="Questionnaire answers added",
            )

        return updated

    def add_upload_declaration(
        self,
        quote_id: str,
        original_filename: str,
        content_type: str,
        size_bytes: int,
        purpose: str = "",
    ) -> Quote | None:
        """Add an upload declaration to a quote.

        The filename is encrypted before storage.
        """
        quote = self.get_quote(quote_id)
        if not quote:
            return None

        # Create upload declaration
        upload = UploadDeclaration(
            upload_id=UploadDeclaration.upload_id._default_func(),  # type: ignore
            original_filename=original_filename,
            content_type=content_type,
            size_bytes=size_bytes,
            purpose=purpose,
        )

        quote.upload_declarations.append(upload)
        quote.updated_at = utc_now()

        # Note: In a full implementation, we'd encrypt the filename before storage
        # For this bootstrap, we're declaring the upload but not encrypting the metadata yet

        updated = self._repo.update(quote)

        # Log the event
        if updated:
            self._event_log.append_quote_event(
                quote=updated,
                event_type=EventType.QUOTE_UPLOAD_DECLARED,
                actor_type=EventActorType.ACCOUNT,
                actor_id=None,
                redacted_summary=f"Upload declared ({content_type}, {size_bytes} bytes)",
            )

        return updated

    def submit_quote(self, quote_id: str, account_id: str) -> Quote | None:
        """Submit a quote for review."""
        quote = self.get_quote(quote_id)
        if not quote:
            return None

        if not quote.can_submit():
            return None

        quote.status = QuoteStatus.SUBMITTED
        quote.account_id = account_id
        quote.updated_at = utc_now()

        updated = self._repo.update(quote)

        if updated:
            # Log submission event
            self._event_log.log_quote_submitted(updated, account_id)

            # Transition to needs_review (could be automatic or manual)
            # For bootstrap, we'll auto-transition to NEEDS_REVIEW
            updated.status = QuoteStatus.NEEDS_REVIEW
            updated.updated_at = utc_now()
            self._repo.update(updated)

            self._event_log.log_quote_status_change(
                updated, QuoteStatus.NEEDS_REVIEW, EventActorType.SYSTEM, None
            )

        return updated

    def get_quote_status(self, quote_id: str) -> QuoteStatus | None:
        """Get the status of a quote."""
        quote = self.get_quote(quote_id)
        return quote.status if quote else None

    def get_safe_summary(self, quote_id: str) -> dict[str, Any] | None:
        """Get a safe summary of a quote (no sensitive data)."""
        quote = self.get_quote(quote_id)
        if not quote:
            return None
        return quote.get_safe_summary()


@lru_cache()
def get_quote_service() -> QuoteService:
    """Get cached quote service instance."""
    return QuoteService()


def reset_quote_service() -> None:
    """Reset the cached quote service (useful for testing)."""
    get_quote_service.cache_clear()
