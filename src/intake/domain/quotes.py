"""Quote domain models."""

import uuid
from datetime import datetime
from enum import StrEnum, auto
from typing import Any

from pydantic import BaseModel, Field

from intake.domain.crypto import EncryptedPayload
from intake.domain.events import EventAggregateType
from intake.domain.time import utc_now


class QuoteServiceLane(StrEnum):
    """Service lanes for quotes."""

    SOFTWARE_SYSTEMS = "software_systems"
    PHOTOGRAPHY = "photography"
    PRACTICAL_HELP = "practical_help"
    UNSURE = "unsure"


class QuoteStatus(StrEnum):
    """Status of a quote."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    NEEDS_REVIEW = "needs_review"
    REVIEWING = "reviewing"
    QUOTED = "quoted"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    CLOSED = "closed"


class UploadDeclaration(BaseModel):
    """Declaration of an upload (metadata only, no binary data)."""

    upload_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    original_filename: str  # Encrypted in storage
    content_type: str
    size_bytes: int
    declaration_time: datetime = Field(default_factory=utc_now)
    purpose: str = ""  # e.g., "portfolio", "reference", "example"


class Quote(BaseModel):
    """Quote domain model."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    # Account that created this quote
    account_id: str | None = None

    # Service lane
    service_lane: QuoteServiceLane | None = None

    # Basic info
    short_summary: str = ""
    detailed_description: str = ""
    preferred_timeline: str | None = None

    # Location info (encrypted)
    general_service_area: str = ""  # Non-sensitive, e.g., "San Francisco Bay Area"
    encrypted_exact_location: EncryptedPayload | None = None  # Encrypted exact address

    # Access notes (encrypted)
    encrypted_access_notes: EncryptedPayload | None = None

    # Questionnaire answers (encrypted)
    encrypted_questionnaire: EncryptedPayload | None = None

    # Upload declarations
    upload_declarations: list[UploadDeclaration] = Field(default_factory=list)

    # Status
    status: QuoteStatus = QuoteStatus.DRAFT

    # Append-only events (not stored directly on quote, but tracked separately)
    # This is a projection convenience for the domain model

    @property
    def aggregate_type(self) -> EventAggregateType:
        """Get the aggregate type for events related to this quote."""
        return EventAggregateType.QUOTE

    def can_submit(self) -> bool:
        """Check if the quote can be submitted."""
        return self.status == QuoteStatus.DRAFT and bool(self.service_lane)

    def can_review(self) -> bool:
        """Check if the quote can be reviewed."""
        return self.status in (QuoteStatus.SUBMITTED, QuoteStatus.NEEDS_REVIEW)

    def get_safe_summary(self) -> dict[str, Any]:
        """Return a summary with no sensitive data."""
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat(),
            "service_lane": self.service_lane,
            "short_summary": self.short_summary,
            "general_service_area": self.general_service_area,
            "status": self.status,
            "upload_count": len(self.upload_declarations),
        }
