"""Cryptography domain models."""

import base64
import hashlib
from typing import Any

from pydantic import BaseModel, Field


class EncryptedPayload(BaseModel):
    """Encrypted payload model."""

    # Ciphertext as base64-encoded bytes
    ciphertext: str = Field(..., description="Base64-encoded ciphertext")
    
    # Initialization vector / nonce as base64-encoded bytes
    nonce: str = Field(..., description="Base64-encoded nonce/IV")
    
    # Tag for authenticated encryption (AES-GCM)
    tag: str | None = Field(default=None, description="Base64-encoded authentication tag")
    
    # Algorithm identifier
    algorithm: str = Field(default="aes-gcm", description="Encryption algorithm used")
    
    # Key version for future key rotation
    key_version: int = Field(default=1, description="Key version for rotation")

    def to_dict(self) -> dict[str, Any]:
        """Return as dictionary."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EncryptedPayload":
        """Create from dictionary."""
        return cls(**data)


class HashLookup(BaseModel):
    """Hash lookup model for deduplication and indexing."""

    # The hashed value (hex digest)
    hash_value: str = Field(..., description="Hex-encoded hash digest")
    
    # The purpose of this hash (to prevent collision attacks)
    purpose: str = Field(..., description="Purpose of the hash (e.g., 'challenge', 'credential_id')")
    
    # Salt used for the hash
    salt: str = Field(..., description="Base64-encoded salt")

    @property
    def lookup_key(self) -> str:
        """Create a composite lookup key."""
        return f"{self.purpose}:{self.hash_value}"
