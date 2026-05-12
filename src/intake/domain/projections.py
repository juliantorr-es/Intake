"""Projection models for safe UI rendering."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from intake.domain.crypto import EncryptedPayload
from intake.domain.quotes import QuoteServiceLane, QuoteStatus


class SafeText(BaseModel):
    """Wrapper for safe text content."""

    content: str

    def render(self) -> str:
        """Return the safe content for rendering."""
        return self.content


class EncryptedField(BaseModel):
    """Projection for an encrypted field."""

    has_content: bool = False
    content_hash: str | None = None  # For change detection without decryption


class UploadProjection(BaseModel):
    """Projection for upload declarations."""

    upload_id: str
    content_type: str
    size_bytes: int
    purpose: str = ""


class QuoteProjection(BaseModel):
    """Safe projection of a quote for UI rendering."""

    id: str
    created_at: datetime
    service_lane: QuoteServiceLane | None = None
    short_summary: str = ""
    general_service_area: str = ""
    status: QuoteStatus = QuoteStatus.DRAFT
    upload_count: int = 0
    uploads: list[UploadProjection] = Field(default_factory=list)

    # Encrypted field indicators (no actual encrypted data exposed)
    has_encrypted_location: bool = False
    has_encrypted_access_notes: bool = False
    has_encrypted_questionnaire: bool = False

    class Config:
        from_attributes = True


class SafeQuoteSummary(BaseModel):
    """Very safe summary for listing quotes."""

    id: str
    created_at: str
    service_lane: str | None = None
    short_summary: str = ""
    general_service_area: str = ""
    status: str = "draft"
    upload_count: int = 0

    @classmethod
    def from_quote(cls, quote: Any) -> "SafeQuoteSummary":
        """Create a safe summary from a quote domain model."""
        return cls(
            id=quote.id,
            created_at=quote.created_at.isoformat(),
            service_lane=quote.service_lane.value if hasattr(quote.service_lane, "value") else quote.service_lane,
            short_summary=quote.short_summary,
            general_service_area=quote.general_service_area,
            status=quote.status.value if hasattr(quote.status, "value") else quote.status,
            upload_count=len(quote.upload_declarations) if quote.upload_declarations else 0,
        )
