"""Sync protocol models for Hosted <-> Local communication."""

import json
from datetime import datetime, timezone
from enum import StrEnum, auto
from typing import Any
from pydantic import BaseModel, Field, ConfigDict


class SyncDirection(StrEnum):
    """Direction of sync."""
    LOCAL_TO_HOSTED = auto()
    HOSTED_TO_LOCAL = auto()


class LocalDevice(BaseModel):
    """Identity of a local operator machine.
    
    This model exists on the Local Console and is used for registration
    with the Hosted Intake backend.
    """
    device_id: str
    display_name: str
    
    # Placeholders for future asymmetric keys
    public_signing_key: str | None = None
    public_encryption_key: str | None = None
    
    # Private material MUST NOT be in this model
    # private_key: str  # <--- NEVER ADD THIS HERE
    
    created_at: datetime = Field(default_factory=datetime.now)
    last_seen_at: datetime = Field(default_factory=datetime.now)
    revoked_at: datetime | None = None
    
    trust_state: str = "pending" # pending, trusted, revoked

    model_config = ConfigDict(extra="forbid")


class HostedRegisteredDevice(BaseModel):
    """A local device that has been registered on the Hosted backend."""
    device_id: str
    display_name: str
    public_signing_key: str | None = None
    public_encryption_key: str | None = None
    
    registered_at: datetime
    last_seen_at: datetime
    revoked_at: datetime | None = None
    
    # Metadata for the sync session
    trust_state: str
    
    model_config = ConfigDict(extra="forbid")


class LocalDeviceSession(BaseModel):
    """Session for an authenticated local device."""
    device_id: str
    session_token: str
    expires_at: datetime


class HostedQuoteProjection(BaseModel):
    """Redacted projection of a quote for the local console to pull.
    
    This model MUST NOT contain any sensitive fields in plaintext or ciphertext.
    It serves as a shallow discovery metadata record.
    """
    quote_id: str
    status: str
    service_lane: str | None = None
    general_service_area: str | None = None
    created_at: datetime
    updated_at: datetime
    has_encrypted_payload: bool
    upload_count: int
    email_verified: bool = False
    decrypted: bool = False
    
    @classmethod
    def from_domain(cls, quote: Any) -> "HostedQuoteProjection":
        return cls(
            quote_id=quote.id,
            status=quote.status,
            service_lane=quote.service_lane,
            general_service_area=quote.general_service_area,
            created_at=quote.created_at,
            updated_at=quote.updated_at,
            has_encrypted_payload=bool(quote.encrypted_exact_location),
            upload_count=len(quote.uploads) if hasattr(quote, "uploads") else 0,
            email_verified=getattr(quote, "email_verified", False),
            decrypted=False # Only Local Console knows if it's decrypted
        )

    # Explicitly excluding sensitive fields to prevent accidental leakage
    model_config = ConfigDict(extra="forbid")


from intake.domain.crypto import EncryptedPayload

class EncryptedQuoteEnvelope(BaseModel):
    """Envelope containing sensitive quote data for local decryption.
    
    This envelope carries the ciphertext that only the Local Console can read.
    It aggregates multiple sensitive fields for a single quote.
    """
    quote_id: str
    encrypted_exact_location: EncryptedPayload | None = None
    encrypted_access_notes: EncryptedPayload | None = None
    encrypted_questionnaire: EncryptedPayload | None = None
    
    # List of encrypted upload metadata
    # (Simplified for now: just the encrypted filenames)
    encrypted_uploads: list[EncryptedPayload] = Field(default_factory=list)
    
    @classmethod
    def from_domain(cls, quote: Any) -> "EncryptedQuoteEnvelope":
        return cls(
            quote_id=quote.id,
            encrypted_exact_location=quote.encrypted_exact_location,
            encrypted_access_notes=quote.encrypted_access_notes,
            encrypted_questionnaire=quote.encrypted_questionnaire,
            encrypted_uploads=[u.encrypted_original_filename for u in quote.uploads] if hasattr(quote, "uploads") else []
        )

    def to_summary(self) -> str:
        fields = []
        if self.encrypted_exact_location: fields.append("location")
        if self.encrypted_access_notes: fields.append("access_notes")
        if self.encrypted_questionnaire: fields.append("questionnaire")
        return f"EncryptedEnvelope(quote_id={self.quote_id}, fields={fields}, uploads={len(self.encrypted_uploads)})"


class LocalDeviceActionEnvelope(BaseModel):
    """A signed action from a Local Console.
    
    This envelope is verified by the Hosted backend to ensure the action
    was authorized by a registered local device.
    """
    action_id: str
    device_id: str
    action_kind: str  # e.g., "quote_review_start", "quote_status_update"
    aggregate_type: str  # e.g., "QUOTE"
    aggregate_id: str
    issued_at: datetime
    nonce: str  # For replay prevention
    payload: dict[str, Any]
    signature: str
    signature_algorithm: str = "ed25519"
    
    model_config = ConfigDict(extra="forbid")

    def get_canonical_payload(self) -> bytes:
        """Return a deterministic JSON representation for signing/verification."""
        # Normalize issued_at to a consistent string format (UTC with Z, millisecond precision)
        ts = self.issued_at.astimezone(timezone.utc)
        issued_at_str = ts.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        
        # We sort keys and ensure no extra whitespace
        data = {
            "action_id": self.action_id,
            "device_id": self.device_id,
            "action_kind": self.action_kind,
            "aggregate_type": self.aggregate_type.lower(),
            "aggregate_id": self.aggregate_id,
            "issued_at": issued_at_str,
            "nonce": self.nonce,
            "payload": self.payload
        }
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return canonical


class LocalOperatorAction(BaseModel):
    """Action taken by a local operator to be synced back to hosted."""
    action_id: str
    quote_id: str
    action_type: str  # e.g., "approve", "request_info", "draft_quote"
    payload: dict[str, Any]
    performed_at: datetime = Field(default_factory=datetime.now)
    signature: str | None = None  # Signed by device key


class SyncEvent(BaseModel):
    """Event generated during synchronization."""
    event_id: str
    timestamp: datetime = Field(default_factory=datetime.now)
    event_type: str
    redacted_summary: str
    details: dict[str, Any] = Field(default_factory=dict)
