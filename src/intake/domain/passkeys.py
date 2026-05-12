"""Passkey domain models."""

import base64
import uuid
from datetime import datetime, timedelta
from enum import StrEnum, auto
from typing import Any

from pydantic import BaseModel, Field

from intake.config import get_settings
from intake.domain.events import EventAggregateType
from intake.domain.time import utc_expired, utc_now


class ChallengeAction(StrEnum):
    """Action type for passkey challenge."""

    REGISTER = auto()
    LOGIN = auto()


class PasskeyChallengeStatus(StrEnum):
    """Status of a passkey challenge."""

    PENDING = auto()
    CONSUMED = auto()
    EXPIRED = auto()


class PasskeyChallenge(BaseModel):
    """Challenge for passkey registration or authentication."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    challenge: str = Field(default_factory=lambda: base64.b64encode(uuid.uuid4().bytes).decode())
    rp_id: str
    origin: str
    action: ChallengeAction
    status: PasskeyChallengeStatus = PasskeyChallengeStatus.PENDING
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime
    consumed_at: datetime | None = None
    attempt_count: int = 0

    # Who this challenge is for (optional, for registration)
    account_id: str | None = None

    @property
    def is_valid(self) -> bool:
        """Check if the challenge is still valid (not consumed, not expired)."""
        settings = get_settings()
        expiry_seconds = settings.intake_challenge_expiry
        now = utc_now()
        return (
            self.status == PasskeyChallengeStatus.PENDING
            and now < self.expires_at
            and (now - self.created_at).total_seconds() < expiry_seconds
        )

    @property
    def is_expired(self) -> bool:
        """Check if the challenge has expired."""
        return utc_now() >= self.expires_at

    @property
    def is_consumed(self) -> bool:
        """Check if the challenge has been consumed."""
        return self.status == PasskeyChallengeStatus.CONSUMED

    @property
    def aggregate_type(self) -> EventAggregateType:
        """Get the aggregate type for events related to passkeys."""
        return EventAggregateType.PASSKEY

    def mark_consumed(self) -> None:
        """Mark the challenge as consumed."""
        self.status = PasskeyChallengeStatus.CONSUMED
        self.consumed_at = utc_now()

    def increment_attempt(self) -> None:
        """Increment the attempt count."""
        self.attempt_count += 1

    @classmethod
    def create_registration_challenge(
        cls,
        rp_id: str,
        origin: str,
        account_id: str | None = None,
        expiry_seconds: int | None = None,
    ) -> "PasskeyChallenge":
        """Create a new registration challenge."""
        settings = get_settings()
        if expiry_seconds is None:
            expiry_seconds = settings.intake_challenge_expiry
        return cls(
            rp_id=rp_id,
            origin=origin,
            action=ChallengeAction.REGISTER,
            account_id=account_id,
            expires_at=utc_now() + timedelta(seconds=expiry_seconds),
        )

    @classmethod
    def create_authentication_challenge(
        cls,
        rp_id: str,
        origin: str,
        account_id: str | None = None,
        expiry_seconds: int | None = None,
    ) -> "PasskeyChallenge":
        """Create a new authentication challenge."""
        settings = get_settings()
        if expiry_seconds is None:
            expiry_seconds = settings.intake_challenge_expiry
        return cls(
            rp_id=rp_id,
            origin=origin,
            action=ChallengeAction.LOGIN,
            account_id=account_id,
            expires_at=utc_now() + timedelta(seconds=expiry_seconds),
        )


class PasskeyType(StrEnum):
    """Type of passkey credential."""

    PUBLIC_KEY = auto()


class PasskeyCredential(BaseModel):
    """Stored passkey credential."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    credential_id: str  # Base64-encoded credential ID (hashed for lookup)
    public_key: str  # Base64-encoded public key
    sign_count: int = 0  # Anti-replay counter
    credential_type: PasskeyType = PasskeyType.PUBLIC_KEY
    account_id: str
    registered_at: datetime = Field(default_factory=utc_now)
    last_used_at: datetime | None = None
    name: str | None = None  # User-friendly name for the credential
    # WebAuthn metadata
    transports: str | None = None  # JSON-serialized list of transports
    backup_eligible: bool = False
    backup_state: bool = False
    device_label: str | None = None
    revoked_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        """Check if credential is active (not revoked)."""
        return self.revoked_at is None


class PasskeyRegistrationOptions(BaseModel):
    """Options for passkey registration and authentication.
    
    This model is reused for both registration and authentication options.
    """

    challenge: str
    rp: dict[str, Any]
    user: dict[str, Any]
    pubKeyCredParams: list[dict[str, Any]]
    authenticatorSelection: dict[str, Any] | None = None
    supportedAlgorithms: list[int] | None = None
    extensions: dict[str, Any] | None = None
    timeout: int | None = None
    allowCredentials: list[dict[str, Any]] | None = None
    userVerification: str | None = None


class PasskeyVerification(BaseModel):
    """Verification data from passkey ceremony."""

    id: str
    raw_id: str
    type: str
    response: dict[str, Any]
