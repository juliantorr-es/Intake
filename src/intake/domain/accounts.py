"""Account domain models."""

import uuid
from datetime import datetime

from pydantic import Field

from intake.domain.events import EventAggregateType


class Account:
    """Account domain model."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # No passwords, no email as primary auth - passkey only
    # Email may be added later as contact/recovery, but not for login

    @property
    def aggregate_type(self) -> EventAggregateType:
        """Get the aggregate type for events related to this account."""
        return EventAggregateType.ACCOUNT


class Session:
    """Active session domain model."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    account_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime
    is_active: bool = True

    # Session tokens are not stored in raw form - only hashed for lookup
    # The actual session identifier is used as a secure cookie
