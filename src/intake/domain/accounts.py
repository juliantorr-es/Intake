"""Account domain models."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from intake.domain.events import EventAggregateType
from intake.domain.time import utc_now


class Account(BaseModel):
    """Account domain model."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    # No passwords, no email as primary auth - passkey only
    # Email may be added later as contact/recovery, but not for login

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
        return self.revoked_at is None and utc_now() < self.expires_at

    @property
    def is_expired(self) -> bool:
        """Check if session has expired."""
        return utc_now() >= self.expires_at

    @property
    def is_revoked(self) -> bool:
        """Check if session has been revoked."""
        return self.revoked_at is not None
