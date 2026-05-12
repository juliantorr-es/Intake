"""SQLModel persistence models."""

import json
from datetime import datetime
from typing import Any

from sqlmodel import Field, SQLModel, Column, JSON, TEXT

from intake.domain.crypto import EncryptedPayload
from intake.domain.events import EventAggregateType, EventType, EventActorType
from intake.domain.passkeys import ChallengeAction, PasskeyChallengeStatus, PasskeyType
from intake.domain.quotes import QuoteServiceLane, QuoteStatus
from intake.domain.time import utc_now


# ========== Account Models ==========


class AccountModel(SQLModel, table=True):
    """Account database model."""

    __tablename__ = "accounts"

    id: str = Field(default=None, primary_key=True, index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    # Email metadata
    encrypted_email: str | None = Field(default=None, sa_column=Column(JSON))
    normalized_email_hash: str | None = Field(default=None, index=True, unique=True)
    email_verified_at: datetime | None = Field(default=None, index=True)

    @classmethod
    def from_domain(cls, account: Any) -> "AccountModel":
        """Create a database model from a domain account."""
        encrypted_email = None
        if account.encrypted_email:
            encrypted_email = json.dumps(account.encrypted_email.model_dump())
        
        return cls(
            id=account.id,
            created_at=account.created_at,
            updated_at=account.updated_at,
            encrypted_email=encrypted_email,
            normalized_email_hash=account.normalized_email_hash,
            email_verified_at=account.email_verified_at,
        )

    def to_domain(self) -> Any:
        """Convert to domain model."""
        from intake.domain.accounts import Account
        from intake.domain.crypto import EncryptedPayload

        encrypted_email = None
        if self.encrypted_email:
            encrypted_email = EncryptedPayload(**json.loads(self.encrypted_email))

        return Account(
            id=self.id,
            created_at=self.created_at,
            updated_at=self.updated_at,
            encrypted_email=encrypted_email,
            normalized_email_hash=self.normalized_email_hash,
            email_verified_at=self.email_verified_at,
        )


# ========== Session Models ==========


class SessionModel(SQLModel, table=True):
    """Session database model.

    Only stores hashed session tokens for lookup. Never stores raw tokens.
    """

    __tablename__ = "sessions"

    id: str = Field(default=None, primary_key=True, index=True)
    account_id: str = Field(foreign_key="accounts.id", index=True)
    token_hash: str = Field(index=True)  # SHA-256 hash for lookup
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime = Field(index=True)
    revoked_at: datetime | None = Field(default=None, index=True)
    last_seen_at: datetime | None = Field(default=None)

    @classmethod
    def from_domain(cls, session: Any) -> "SessionModel":
        """Create a database model from a domain session."""
        return cls(
            id=session.id,
            account_id=session.account_id,
            token_hash=session.token_hash,
            created_at=session.created_at,
            expires_at=session.expires_at,
            revoked_at=session.revoked_at,
            last_seen_at=session.last_seen_at,
        )

    def to_domain(self) -> Any:
        """Convert to domain model."""
        from intake.domain.accounts import Session
        return Session(
            id=self.id,
            account_id=self.account_id,
            token_hash=self.token_hash,
            created_at=self.created_at,
            expires_at=self.expires_at,
            revoked_at=self.revoked_at,
            last_seen_at=self.last_seen_at,
        )


# ========== Passkey Models ==========


class PasskeyChallengeModel(SQLModel, table=True):
    """Passkey challenge database model for WebAuthn ceremonies."""

    __tablename__ = "passkey_challenges"

    id: str = Field(default=None, primary_key=True, index=True)
    challenge: str = Field()  # Base64-encoded challenge value
    rp_id: str = Field(index=True)
    origin: str = Field(index=True)
    action: ChallengeAction = Field(index=True)  # register or login
    status: PasskeyChallengeStatus = Field(default=PasskeyChallengeStatus.PENDING, index=True)
    account_id: str | None = Field(default=None, foreign_key="accounts.id", index=True)
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime = Field(index=True)
    consumed_at: datetime | None = Field(default=None, index=True)
    attempt_count: int = Field(default=0)


class PasskeyCredentialModel(SQLModel, table=True):
    """Passkey credential database model."""

    __tablename__ = "passkey_credentials"

    id: str = Field(default=None, primary_key=True, index=True)
    credential_id: str = Field(index=True)  # Base64-encoded, hashed for lookup
    public_key: str = Field(sa_column=Column(TEXT))  # Base64-encoded
    sign_count: int = Field(default=0)  # Anti-replay counter
    credential_type: PasskeyType = Field(default=PasskeyType.PUBLIC_KEY)
    account_id: str = Field(foreign_key="accounts.id", index=True)
    registered_at: datetime = Field(default_factory=utc_now)
    last_used_at: datetime | None = Field(default=None)
    name: str | None = Field(default=None)
    # WebAuthn metadata
    transports: str | None = Field(default=None, sa_column=Column(JSON))  # List of transports
    backup_eligible: bool = Field(default=False)
    backup_state: bool = Field(default=False)
    device_label: str | None = Field(default=None)
    revoked_at: datetime | None = Field(default=None, index=True)


# ========== Email Verification Models ==========


class EmailVerificationCodeModel(SQLModel, table=True):
    """Email verification code database model."""

    __tablename__ = "email_verification_codes"

    id: str = Field(default=None, primary_key=True, index=True)
    account_id: str = Field(foreign_key="accounts.id", index=True)
    email_hash: str = Field(index=True)
    code_hash: str = Field(index=True)
    attempts: int = Field(default=0)
    max_attempts: int = Field(default=5)
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime = Field(index=True)
    consumed_at: datetime | None = Field(default=None, index=True)

    @classmethod
    def from_domain(cls, code: Any) -> "EmailVerificationCodeModel":
        """Create a database model from a domain code."""
        return cls(
            id=code.id,
            account_id=code.account_id,
            email_hash=code.email_hash,
            code_hash=code.code_hash,
            attempts=code.attempts,
            max_attempts=code.max_attempts,
            created_at=code.created_at,
            expires_at=code.expires_at,
            consumed_at=code.consumed_at,
        )

    def to_domain(self) -> Any:
        """Convert to domain model."""
        from intake.domain.accounts import EmailVerificationCode
        return EmailVerificationCode(
            id=self.id,
            account_id=self.account_id,
            email_hash=self.email_hash,
            code_hash=self.code_hash,
            attempts=self.attempts,
            max_attempts=self.max_attempts,
            created_at=self.created_at,
            expires_at=self.expires_at,
            consumed_at=self.consumed_at,
        )


# ========== Quote Models ==========


class UploadModel(SQLModel, table=True):
    """Upload database model."""

    __tablename__ = "uploads"

    id: str = Field(default=None, primary_key=True, index=True)
    quote_id: str = Field(foreign_key="quotes.id", index=True)
    account_id: str = Field(foreign_key="accounts.id", index=True)
    storage_object_id: str = Field(index=True)
    storage_relative_path: str = Field()
    encrypted_original_filename: str = Field(sa_column=Column(JSON))  # EncryptedPayload as JSON
    declared_content_type: str = Field()
    extension: str = Field()
    size_bytes: int = Field()
    status: str = Field(default="accepted", index=True)
    created_at: datetime = Field(default_factory=utc_now)
    deleted_at: datetime | None = Field(default=None, index=True)

    @classmethod
    def from_domain(cls, upload: Any) -> "UploadModel":
        """Create a database model from a domain upload."""
        return cls(
            id=upload.id,
            quote_id=upload.quote_id,
            account_id=upload.account_id,
            storage_object_id=upload.storage_object_id,
            storage_relative_path=upload.storage_relative_path,
            encrypted_original_filename=json.dumps(upload.encrypted_original_filename.model_dump()),
            declared_content_type=upload.declared_content_type,
            extension=upload.extension,
            size_bytes=upload.size_bytes,
            status=upload.status,
            created_at=upload.created_at,
            deleted_at=upload.deleted_at,
        )

    def to_domain(self) -> Any:
        """Convert to domain model."""
        from intake.domain.quotes import Upload, UploadStatus
        from intake.domain.crypto import EncryptedPayload

        return Upload(
            id=self.id,
            quote_id=self.quote_id,
            account_id=self.account_id,
            storage_object_id=self.storage_object_id,
            storage_relative_path=self.storage_relative_path,
            encrypted_original_filename=EncryptedPayload(**json.loads(self.encrypted_original_filename)),
            declared_content_type=self.declared_content_type,
            extension=self.extension,
            size_bytes=self.size_bytes,
            status=UploadStatus(self.status),
            created_at=self.created_at,
            deleted_at=self.deleted_at,
        )


class QuoteModel(SQLModel, table=True):
    """Quote database model."""

    __tablename__ = "quotes"

    id: str = Field(default=None, primary_key=True, index=True)
    account_id: str | None = Field(default=None, foreign_key="accounts.id", index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    # Service lane
    service_lane: QuoteServiceLane | None = Field(default=None)

    # Basic info
    short_summary: str = Field(default="")
    detailed_description: str = Field(default="", sa_column=Column(TEXT))
    preferred_timeline: str | None = Field(default=None)

    # Location info
    general_service_area: str = Field(default="")
    encrypted_exact_location: str | None = Field(
        default=None, sa_column=Column(JSON)
    )  # EncryptedPayload as JSON string

    # Access notes
    encrypted_access_notes: str | None = Field(
        default=None, sa_column=Column(JSON)
    )  # EncryptedPayload as JSON string

    # Questionnaire
    encrypted_questionnaire: str | None = Field(
        default=None, sa_column=Column(JSON)
    )  # EncryptedPayload as JSON string

    # Status
    status: QuoteStatus = Field(default=QuoteStatus.DRAFT, index=True)

    @classmethod
    def from_domain(cls, quote: Any) -> "QuoteModel":
        """Create a database model from a domain quote."""
        encrypted_location = None
        encrypted_access = None
        encrypted_questionnaire = None

        if quote.encrypted_exact_location:
            encrypted_location = json.dumps(quote.encrypted_exact_location.model_dump())
        if quote.encrypted_access_notes:
            encrypted_access = json.dumps(quote.encrypted_access_notes.model_dump())
        if quote.encrypted_questionnaire:
            encrypted_questionnaire = json.dumps(quote.encrypted_questionnaire.model_dump())

        return cls(
            id=quote.id,
            account_id=quote.account_id,
            created_at=quote.created_at,
            updated_at=quote.updated_at,
            service_lane=quote.service_lane,
            short_summary=quote.short_summary,
            detailed_description=quote.detailed_description,
            preferred_timeline=quote.preferred_timeline,
            general_service_area=quote.general_service_area,
            encrypted_exact_location=encrypted_location,
            encrypted_access_notes=encrypted_access,
            encrypted_questionnaire=encrypted_questionnaire,
            status=quote.status,
        )

    def to_domain(self) -> Any:
        """Convert to domain model."""
        from intake.domain.crypto import EncryptedPayload
        from intake.domain.quotes import Quote

        encrypted_location = None
        encrypted_access = None
        encrypted_questionnaire = None

        if self.encrypted_exact_location:
            encrypted_location = EncryptedPayload(**json.loads(self.encrypted_exact_location))
        if self.encrypted_access_notes:
            encrypted_access = EncryptedPayload(**json.loads(self.encrypted_access_notes))
        if self.encrypted_questionnaire:
            encrypted_questionnaire = EncryptedPayload(
                **json.loads(self.encrypted_questionnaire)
            )

        return Quote(
            id=self.id,
            account_id=self.account_id,
            created_at=self.created_at,
            updated_at=self.updated_at,
            service_lane=self.service_lane,
            short_summary=self.short_summary,
            detailed_description=self.detailed_description,
            preferred_timeline=self.preferred_timeline,
            general_service_area=self.general_service_area,
            encrypted_exact_location=encrypted_location,
            encrypted_access_notes=encrypted_access,
            encrypted_questionnaire=encrypted_questionnaire,
            status=self.status,
            uploads=[], # To be populated by repository
        )


# ========== Event Models ==========


class EventModel(SQLModel, table=True):
    """Event database model."""

    __tablename__ = "events"

    id: str = Field(default=None, primary_key=True, index=True)
    aggregate_type: EventAggregateType = Field(index=True)
    aggregate_id: str = Field(index=True)
    event_type: EventType = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now)
    actor_type: EventActorType | None = Field(default=None)
    actor_id: str | None = Field(default=None, index=True)
    redacted_summary: str = Field(default="")
    encrypted_payload: str | None = Field(
        default=None, sa_column=Column(JSON)
    )  # EncryptedPayload as JSON string

    # Events are append-only and immutable
    class Config:
        populate_by_name = True

    @classmethod
    def from_domain(cls, event: Any) -> "EventModel":
        """Create a database model from a domain event."""
        encrypted_payload_json = None
        if event.encrypted_payload:
            # event.encrypted_payload might be EncryptedPayload or str
            if hasattr(event.encrypted_payload, "model_dump"):
                encrypted_payload_json = json.dumps(event.encrypted_payload.model_dump())
            else:
                encrypted_payload_json = event.encrypted_payload

        return cls(
            id=event.event_id,
            aggregate_type=event.aggregate_type,
            aggregate_id=event.aggregate_id,
            event_type=event.event_type,
            created_at=event.created_at,
            actor_type=event.actor_type,
            actor_id=event.actor_id,
            redacted_summary=event.redacted_summary,
            encrypted_payload=encrypted_payload_json,
        )

    def to_domain(self) -> Any:
        """Convert to domain model."""
        from intake.domain.crypto import EncryptedPayload
        from intake.domain.events import Event

        encrypted_payload = None
        if self.encrypted_payload:
            encrypted_payload = EncryptedPayload(**json.loads(self.encrypted_payload))

        return Event(
            event_id=self.id,
            aggregate_type=self.aggregate_type,
            aggregate_id=self.aggregate_id,
            event_type=self.event_type,
            created_at=self.created_at,
            actor_type=self.actor_type,
            actor_id=self.actor_id,
            redacted_summary=self.redacted_summary,
            encrypted_payload=json.dumps(encrypted_payload.model_dump()) if encrypted_payload else None,
        )
