"""Account domain models."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from intake.domain.crypto import EncryptedPayload
from intake.domain.events import EventAggregateType
from intake.domain.time import utc_now


class Account(BaseModel):
    """Account domain model."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    # No passwords, no email as primary auth - passkey only
    # Email may be added later as contact/recovery, but not for login
    encrypted_email: EncryptedPayload | None = None
    normalized_email_hash: str | None = None
    email_verified_at: datetime | None = None

    @property
    def email_status(self) -> str:
        """Return email status summary."""
        if not self.normalized_email_hash:
            return "none"
        if not self.email_verified_at:
            return "pending"
        return "verified"

    @property
    def aggregate_type(self) -> EventAggregateType:
        """Get the aggregate type for events related to this account."""
        return EventAggregateType.ACCOUNT


class Session(BaseModel):
    """Active session domain model.

    Session tokens are NOT stored in raw form - only the hash is stored for lookup.
    The actual session identifier is returned to the client once (via secure cookie).
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    account_id: str
    token_hash: str  # SHA-256 hash of the session token (for lookup)
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime
    revoked_at: datetime | None = None
    last_seen_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        """Check if session is active (not expired, not revoked)."""
        from intake.domain.time import utc_is_before, as_aware_utc
        if self.revoked_at is not None:
            return False
        # Normalize expires_at which may be naive from DB
        return utc_is_before(utc_now(), as_aware_utc(self.expires_at))

    @property
    def is_expired(self) -> bool:
        """Check if session has expired."""
        from intake.domain.time import utc_is_expired, as_aware_utc
        return utc_is_expired(as_aware_utc(self.expires_at))

    @property
    def is_revoked(self) -> bool:
        """Check if session has been revoked."""
        return self.revoked_at is not None


class EmailVerificationCode(BaseModel):
    """Email verification code domain model."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    account_id: str
    email_hash: str  # Hash of normalized email for lookup
    code_hash: str  # Hash of the verification code
    attempts: int = 0
    max_attempts: int = 5
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime
    consumed_at: datetime | None = None

    @property
    def is_expired(self) -> bool:
        """Check if code has expired."""
        from intake.domain.time import utc_is_expired, as_aware_utc
        return utc_is_expired(as_aware_utc(self.expires_at))

    @property
    def can_attempt(self) -> bool:
        """Check if more attempts are allowed."""
        return self.attempts < self.max_attempts and not self.consumed_at and not self.is_expired
