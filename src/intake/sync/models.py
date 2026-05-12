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
    """Redacted projection of a quote for the local console to pull."""
    quote_id: str
    status: str
    service_lane: str | None = None
    general_service_area: str | None = None
    created_at: datetime
    updated_at: datetime
    has_encrypted_payload: bool
    upload_count: int


class EncryptedQuoteEnvelope(BaseModel):
    """Envelope containing sensitive quote data for local decryption."""
    quote_id: str
    ciphertext: str  # Base64 encoded
    nonce: str
    tag: str | None = None


class LocalOperatorAction(BaseModel):
    """Action taken by a local operator to be synced back to hosted."""
    action_id: str
    quote_id: str
    action_type: str
    payload: dict[str, Any]
    performed_at: datetime = Field(default_factory=datetime.now)
    signature: str | None = None  # Signed by device key


class SyncEvent(BaseModel):
    """Event generated during synchronization."""
    event_id: str
    timestamp: datetime = Field(default_factory=datetime.now)
    event_type: str
    details: dict[str, Any]
