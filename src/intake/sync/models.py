"""Sync protocol models for Hosted <-> Local communication."""

from datetime import datetime
from enum import StrEnum, auto
from typing import Any
from pydantic import BaseModel, Field


class SyncDirection(StrEnum):
    """Direction of sync."""
    LOCAL_TO_HOSTED = auto()
    HOSTED_TO_LOCAL = auto()


class LocalDeviceRegistration(BaseModel):
    """Registration for a local operator device."""
    device_id: str
    public_key: str
    registered_at: datetime = Field(default_factory=datetime.now)
    name: str | None = None


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
    
    # Explicitly excluding sensitive fields to prevent accidental leakage
    # during serialization if the domain model is mapped to this.
    class Config:
        extra = "forbid"


class EncryptedQuoteEnvelope(BaseModel):
    """Envelope containing sensitive quote data for local decryption.
    
    This envelope carries the ciphertext that only the Local Console can read.
    """
    quote_id: str
    ciphertext: str  # Base64 encoded
    nonce: str
    tag: str | None = None
    
    def to_summary(self) -> str:
        return f"EncryptedEnvelope(quote_id={self.quote_id}, len={len(self.ciphertext)})"


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
