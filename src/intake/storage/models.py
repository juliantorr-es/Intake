"""SQLModel persistence models."""

import json
from datetime import datetime
from typing import Any

from sqlmodel import Field, SQLModel, Column, JSON, TEXT

from intake.domain.crypto import EncryptedPayload
from intake.domain.events import EventAggregateType, EventType, EventActorType
from intake.domain.passkeys import PasskeyChallengeStatus, PasskeyType
from intake.domain.quotes import QuoteServiceLane, QuoteStatus, UploadDeclaration


# ========== Account Models ==========


class AccountModel(SQLModel, table=True):
    """Account database model."""

    __tablename__ = "accounts"

    id: str = Field(default=None, primary_key=True, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ========== Passkey Models ==========


class PasskeyCredentialModel(SQLModel, table=True):
    """Passkey credential database model."""

    __tablename__ = "passkey_credentials"

    id: str = Field(default=None, primary_key=True, index=True)
    credential_id: str = Field(index=True)  # Base64-encoded, hashed for lookup
    public_key: str = Field(sa_column=Column(TEXT))  # Base64-encoded
    counter: int = Field(default=0)
    credential_type: PasskeyType = Field(default=PasskeyType.PUBLIC_KEY)
    account_id: str = Field(foreign_key="accounts.id", index=True)
    registered_at: datetime = Field(default_factory=datetime.utcnow)
    last_used_at: datetime | None = Field(default=None)
    name: str | None = Field(default=None)


# ========== Session Models ==========


class SessionModel(SQLModel, table=True):
    """Session database model."""

    __tablename__ = "sessions"

    id: str = Field(default=None, primary_key=True, index=True)
    account_id: str = Field(foreign_key="accounts.id", index=True)
    session_hash: str = Field(index=True)  # Hashed session token for lookup
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime = Field(index=True)
    is_active: bool = Field(default=True)


# ========== Quote Models ==========


class UploadDeclarationModel(SQLModel, table=True):
    """Upload declaration database model."""

    __tablename__ = "upload_declarations"

    id: str = Field(default=None, primary_key=True, index=True)
    quote_id: str = Field(foreign_key="quotes.id", index=True)
    upload_id: str = Field(index=True)
    encrypted_filename: str = Field(sa_column=Column(TEXT))  # Encrypted original filename
    content_type: str = Field(default="")
    size_bytes: int = Field(default=0)
    declaration_time: datetime = Field(default_factory=datetime.utcnow)
    purpose: str = Field(default="")
    encrypted_metadata: str | None = Field(
        default=None, sa_column=Column(JSON)
    )  # Additional encrypted metadata as JSON string


class QuoteModel(SQLModel, table=True):
    """Quote database model."""

    __tablename__ = "quotes"

    id: str = Field(default=None, primary_key=True, index=True)
    account_id: str | None = Field(default=None, foreign_key="accounts.id", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

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
        """Convert to domain model. Returns dict for now, will be Quote once circular import is resolved."""
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

        # TODO: Load upload declarations
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
        )


# ========== Event Models ==========


class EventModel(SQLModel, table=True):
    """Event database model."""

    __tablename__ = "events"

    id: str = Field(default=None, primary_key=True, index=True)
    aggregate_type: EventAggregateType = Field(index=True)
    aggregate_id: str = Field(index=True)
    event_type: EventType = Field(index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
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
            encrypted_payload={"ciphertext": encrypted_payload.ciphertext, "nonce": encrypted_payload.nonce, "tag": encrypted_payload.tag, "algorithm": encrypted_payload.algorithm, "key_version": encrypted_payload.key_version} if encrypted_payload else None,
        )
