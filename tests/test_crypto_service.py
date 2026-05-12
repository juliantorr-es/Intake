"""Tests for crypto service."""

import base64
import secrets

import pytest

from intake.config import reset_settings
from intake.domain.crypto import EncryptedPayload
from intake.services.crypto_service import CryptoService, reset_crypto_service


@pytest.fixture(autouse=True)
def reset_caches():
    """Reset caches before and after tests."""
    reset_crypto_service()
    reset_settings()
    yield
    reset_crypto_service()
    reset_settings()


def test_generate_local_dev_key():
    """Test that generated key is valid base64 and 32 bytes."""
    key = CryptoService.generate_local_dev_key()
    # Decode the base64 to check length
    decoded = base64.urlsafe_b64decode(key)
    assert len(decoded) == 32


def test_encrypt_decrypt_roundtrip():
    """Test that encryption and decryption work correctly."""
    # Use a test key
    test_key = secrets.token_bytes(32)
    service = CryptoService(encryption_key=test_key)

    payload = {"secret": "value", "nested": {"key": "data"}, "number": 42}

    encrypted = service.encrypt_json(payload)
    assert isinstance(encrypted, EncryptedPayload)
    assert encrypted.ciphertext != ""
    assert encrypted.nonce != ""
    assert encrypted.tag is not None

    decrypted = service.decrypt_json(encrypted)
    assert decrypted == payload


def test_encrypt_decrypt_different_payloads():
    """Test encryption/decryption with multiple different payloads."""
    test_key = secrets.token_bytes(32)
    service = CryptoService(encryption_key=test_key)

    payloads = [
        {},
        {"empty": ""},
        {"key": "value"},
        {"nested": {"deep": {"value": 123}}},
        {"array": [1, 2, 3, {"obj": True}]},
        {"unicode": "Hello 世界 🌍"},
        {"null": None, "bool": True, "float": 3.14},
    ]

    for payload in payloads:
        encrypted = service.encrypt_json(payload)
        decrypted = service.decrypt_json(encrypted)
        assert decrypted == payload, f"Failed for payload: {payload}"


def test_decrypt_with_wrong_key_fails():
    """Test that decryption with wrong key fails."""
    key1 = secrets.token_bytes(32)
    key2 = secrets.token_bytes(32)

    service1 = CryptoService(encryption_key=key1)
    service2 = CryptoService(encryption_key=key2)

    payload = {"secret": "data"}
    encrypted = service1.encrypt_json(payload)

    with pytest.raises(ValueError, match="Decryption failed"):
        service2.decrypt_json(encrypted)


def test_hash_lookup_value_deterministic():
    """Test that hash_lookup_value is deterministic."""
    value = "test-value-123"
    purpose = "test-purpose"

    hash1 = CryptoService.hash_lookup_value(value, purpose)
    hash2 = CryptoService.hash_lookup_value(value, purpose)

    assert hash1 == hash2


def test_hash_lookup_value_different_purposes():
    """Test that different purposes produce different hashes."""
    value = "test-value-123"

    hash1 = CryptoService.hash_lookup_value(value, "purpose1")
    hash2 = CryptoService.hash_lookup_value(value, "purpose2")

    assert hash1 != hash2


def test_hash_lookup_value_different_values():
    """Test that different values produce different hashes."""
    purpose = "test-purpose"

    hash1 = CryptoService.hash_lookup_value("value1", purpose)
    hash2 = CryptoService.hash_lookup_value("value2", purpose)

    assert hash1 != hash2


def test_hash_lookup_value_hex_format():
    """Test that hash is in hex format."""
    hash_value = CryptoService.hash_lookup_value("test", "test")
    # Hex string should be 64 characters (32 bytes)
    assert len(hash_value) == 64
    # All characters should be hex digits
    assert all(c in "0123456789abcdef" for c in hash_value)


def test_encrypted_payload_is_base64():
    """Test that encrypted payload fields are valid base64."""
    test_key = secrets.token_bytes(32)
    service = CryptoService(encryption_key=test_key)

    payload = {"test": "value"}
    encrypted = service.encrypt_json(payload)

    # All fields should be valid base64
    base64.urlsafe_b64decode(encrypted.ciphertext.encode())
    base64.urlsafe_b64decode(encrypted.nonce.encode())
    if encrypted.tag:
        base64.urlsafe_b64decode(encrypted.tag.encode())
