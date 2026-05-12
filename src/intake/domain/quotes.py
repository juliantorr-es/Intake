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


class UploadStatus(StrEnum):
    """Status of an upload."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DELETED = "deleted"


class Upload(BaseModel):
    """Metadata for an uploaded file."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    quote_id: str
    account_id: str
    storage_object_id: str  # Random unguessable ID for the filename on disk
    storage_relative_path: str  # Relative path from upload root
    encrypted_original_filename: EncryptedPayload
    declared_content_type: str
    extension: str
    size_bytes: int
    status: UploadStatus = UploadStatus.ACCEPTED
    created_at: datetime = Field(default_factory=utc_now)
    deleted_at: datetime | None = None

    def get_safe_summary(self) -> dict[str, Any]:
        """Return a summary with no sensitive data."""
        return {
            "upload_id": self.id,
            "quote_id": self.quote_id,
            "status": self.status,
            "extension": self.extension,
            "declared_content_type": self.declared_content_type,
            "size_bytes": self.size_bytes,
            "created_at": self.created_at.isoformat(),
        }


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

    # Uploads
    uploads: list[Upload] = Field(default_factory=list)

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
            "upload_count": len(self.uploads),
        }
