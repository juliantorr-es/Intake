"""Quote domain models."""

import uuid
from datetime import datetime, timedelta
from enum import StrEnum, auto
from typing import Any, Optional

from pydantic import BaseModel, Field

from intake.domain.crypto import EncryptedPayload
from intake.domain.events import EventAggregateType
from intake.domain.time import utc_now
from intake.deploy.models_upload import UploadProviderKind


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


# =============================================================================
# Upload Session Models (Hosted Upload Broker)
# =============================================================================

class UploadSessionStatus(StrEnum):
    """Status of an upload session."""
    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"
    COMPLETED = "completed"
    REVOKED = "revoked"


class UploadReceiptStatus(StrEnum):
    """Status of an upload receipt."""
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    INVALID = "invalid"


class UploadSession(BaseModel):
    """Hosted upload session for client uploads.
    
    The broker creates short-lived upload sessions that authorize clients
    to upload files to a specific provider. The session contains routing
    metadata but does NOT contain credentials or local paths.
    """
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    quote_id: str
    account_id: str
    
    # Route decision
    chosen_provider: UploadProviderKind
    route_priority: int
    route_reason: str
    
    # Upload constraints
    max_file_size_bytes: int = 150 * 1024 * 1024  # 150MB default
    max_files: int = 20
    allowed_content_types: list[str] = [
        "image/jpeg", "image/png", "image/webp", "image/heic",
        "video/mp4", "video/quicktime",
        "application/pdf",
    ]
    allowed_extensions: list[str] = [
        ".jpg", ".jpeg", ".png", ".webp", ".heic",
        ".mp4", ".mov",
        ".pdf",
    ]
    
    # Session metadata
    upload_endpoint: str
    expires_at: datetime
    created_at: datetime = Field(default_factory=utc_now)
    status: UploadSessionStatus = UploadSessionStatus.PENDING
    
    # Route metadata (does not contain credentials)
    route_metadata: dict[str, Any] = Field(default_factory=dict)
    
    def get_safe_summary(self) -> dict[str, Any]:
        """Return a summary with no sensitive data."""
        return {
            "session_id": self.id,
            "quote_id": self.quote_id,
            "provider": self.chosen_provider.value,
            "route_priority": self.route_priority,
            "route_reason": self.route_reason,
            "max_file_size_bytes": self.max_file_size_bytes,
            "max_files": self.max_files,
            "allowed_content_types": self.allowed_content_types,
            "allowed_extensions": self.allowed_extensions,
            "upload_endpoint": self.upload_endpoint,
            "expires_at": self.expires_at.isoformat(),
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
        }
    
    def is_expired(self) -> bool:
        """Check if session has expired."""
        return self.status == UploadSessionStatus.EXPIRED or self.expires_at < utc_now()
    
    def is_active(self) -> bool:
        """Check if session is active."""
        return self.status == UploadSessionStatus.ACTIVE and not self.is_expired()


class UploadReceipt(BaseModel):
    """Receipt for a completed upload from a provider.
    
    Receipts are created by providers (e.g., Local Receiver) upon successful
    file upload. They contain verification metadata (SHA256, size) but NO
    original filenames or absolute local paths.
    """
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    upload_session_id: str
    quote_id: str
    account_id: str
    
    # Provider information
    provider: UploadProviderKind
    
    # File metadata (NO original filename or local paths)
    storage_object_id: str  # Random unguessable ID, not original filename
    size_bytes: int
    sha256: str  # SHA256 hash of file content
    declared_content_type: str
    extension: str  # Only extension, no full filename
    
    # Status
    status: UploadReceiptStatus = UploadReceiptStatus.PENDING
    
    # Timestamps
    received_at: datetime = Field(default_factory=utc_now)
    processed_at: Optional[datetime] = None
    
    # Rejection reason (if rejected)
    rejection_reason: Optional[str] = None
    
    # Signature verification (future)
    signature: Optional[str] = None
    signed_by_device_id: Optional[str] = None
    
    def get_safe_summary(self) -> dict[str, Any]:
        """Return a summary with no sensitive data.
        
        Does NOT include: original filename, local paths, credential info
        """
        return {
            "receipt_id": self.id,
            "upload_session_id": self.upload_session_id,
            "quote_id": self.quote_id,
            "provider": self.provider.value,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256[:16] + "..." if self.sha256 else "",  # Truncated in summary
            "declared_content_type": self.declared_content_type,
            "extension": self.extension,
            "status": self.status.value,
            "received_at": self.received_at.isoformat(),
        }
    
    def is_valid(self) -> bool:
        """Check if receipt is valid (accepted and not invalid)."""
        return self.status == UploadReceiptStatus.ACCEPTED
