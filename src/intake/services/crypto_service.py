"""Cryptography service for encryption and hashing."""

import base64
import hashlib
import json
import os
import secrets
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from intake.config import get_settings
from intake.domain.crypto import EncryptedPayload


class CryptoService:
    """Service for encryption and hashing operations.

    Security notes:
    - Hashing is for lookup/deduplication only
    - Encryption is for data that needs to be read later
    - Production key management is intentionally not solved here
    - Uses Fernet (AES-CBC with HMAC) for simplicity in bootstrap
    """

    def __init__(self, encryption_key: bytes | None = None):
        """Initialize crypto service.

        Args:
            encryption_key: 32-byte key for encryption. If None, tries to get from settings.
        """
        if encryption_key is None:
            settings = get_settings()
            key_value = settings.intake_dev_encryption_key
            if key_value is None:
                raise ValueError(
                    "No encryption key provided and INTAKE_DEV_ENCRYPTION_KEY not set in environment. "
                    "Generate with: openssl rand -base64 32"
                )
            # Decode from base64
            key_bytes = base64.urlsafe_b64decode(key_value.get_secret_value())
            if len(key_bytes) < 32:
                raise ValueError("Encryption key must be at least 32 bytes")
            # Use first 32 bytes
            encryption_key = key_bytes[:32]

        self._encryption_key = encryption_key
        self._fernet = Fernet(base64.urlsafe_b64encode(encryption_key))

    @staticmethod
    def generate_local_dev_key() -> str:
        """Generate a new encryption key for local development.

        Returns:
            Base64-encoded 32-byte key suitable for INTAKE_DEV_ENCRYPTION_KEY
        """
        key = secrets.token_bytes(32)
        return base64.urlsafe_b64encode(key).decode()

    @staticmethod
    def hash_lookup_value(value: str, purpose: str) -> str:
        """Hash a value for lookup/deduplication purposes.

        Uses SHA-256 with purpose as pepper/salt to prevent collision attacks
        between different purposes.

        Args:
            value: The value to hash
            purpose: The purpose of this hash (e.g., 'challenge', 'credential_id')

        Returns:
            Hex-encoded SHA-256 hash of (purpose + '|' + value)
        """
        combined = f"{purpose}|{value}"
        hash_digest = hashlib.sha256(combined.encode()).hexdigest()
        return hash_digest

    def encrypt_json(self, payload: dict[str, Any]) -> EncryptedPayload:
        """Encrypt a JSON-serializable dictionary.

        Args:
            payload: Dictionary to encrypt

        Returns:
            EncryptedPayload with ciphertext, nonce/IV, tag, and algorithm
        """
        # Serialize to JSON
        json_str = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        json_bytes = json_str.encode()

        # Generate a random 16-byte nonce
        nonce = secrets.token_bytes(12)  # 96 bits for AES-GCM

        # Use AES-GCM with 256-bit key
        aesgcm = AESGCM(self._encryption_key)

        # Encrypt
        ciphertext = aesgcm.encrypt(nonce, json_bytes, None)

        # Split ciphertext and tag (last 16 bytes are the authentication tag for AES-GCM)
        # Actually, AESGCM.encrypt returns ciphertext + tag concatenated
        # For AES-GCM, the tag is 16 bytes
        tag_length = 16
        actual_ciphertext = ciphertext[:-tag_length]
        tag = ciphertext[-tag_length:]

        return EncryptedPayload(
            ciphertext=base64.urlsafe_b64encode(actual_ciphertext).decode(),
            nonce=base64.urlsafe_b64encode(nonce).decode(),
            tag=base64.urlsafe_b64encode(tag).decode(),
            algorithm="aes-gcm",
            key_version=1,
        )

    def encrypt_string(self, text: str) -> EncryptedPayload:
        """Encrypt a simple string.

        Args:
            text: String to encrypt

        Returns:
            EncryptedPayload
        """
        return self.encrypt_json({"value": text})

    def decrypt_json(self, encrypted: EncryptedPayload) -> dict[str, Any]:
        """Decrypt an encrypted JSON payload.

        Args:
            encrypted: EncryptedPayload to decrypt

        Returns:
            Decrypted dictionary

        Raises:
            ValueError: If decryption fails (wrong key, tampered data, etc.)
        """
        # Decode from base64
        ciphertext = base64.urlsafe_b64decode(encrypted.ciphertext.encode())
        nonce = base64.urlsafe_b64decode(encrypted.nonce.encode())
        tag = base64.urlsafe_b64decode(encrypted.tag.encode()) if encrypted.tag else b""

        # Reconstruct full ciphertext + tag
        full_ciphertext = ciphertext + tag

        # Decrypt
        aesgcm = AESGCM(self._encryption_key)

        try:
            plaintext = aesgcm.decrypt(nonce, full_ciphertext, None)
            return json.loads(plaintext.decode())
        except Exception as e:
            raise ValueError(f"Decryption failed: {e}") from e

    def decrypt_string(self, encrypted: EncryptedPayload) -> str:
        """Decrypt an encrypted string.

        Args:
            encrypted: EncryptedPayload to decrypt

        Returns:
            Decrypted string
        """
        decrypted = self.decrypt_json(encrypted)
        return str(decrypted.get("value", ""))


@lru_cache()
def get_crypto_service() -> CryptoService:
    """Get cached crypto service instance."""
    return CryptoService()


def reset_crypto_service() -> None:
    """Reset the cached crypto service (useful for testing)."""
    get_crypto_service.cache_clear()
