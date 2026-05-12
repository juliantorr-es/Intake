"""Tests for Local Device identity models and redaction."""

import pytest
from datetime import datetime
from intake.sync.models import LocalDevice, HostedRegisteredDevice, EncryptedQuoteEnvelope
from intake.domain.crypto import EncryptedPayload

def test_local_device_model_forbids_extra():
    """Verify that LocalDevice forbids extra fields (like accidental private keys)."""
    with pytest.raises(ValueError):
        LocalDevice(
            device_id="dev-1",
            display_name="My Laptop",
            private_key="SHOULD_NOT_BE_HERE" # type: ignore
        )

def test_local_device_serialization():
    """Verify standard serialization of LocalDevice."""
    device = LocalDevice(
        device_id="dev-1",
        display_name="My Laptop",
        public_encryption_key="pub-123"
    )
    data = device.model_dump()
    assert data["device_id"] == "dev-1"
    assert data["public_encryption_key"] == "pub-123"
    assert "private_key" not in data

def test_hosted_registered_device_redaction():
    """Verify that HostedRegisteredDevice only contains public info."""
    device = HostedRegisteredDevice(
        device_id="dev-1",
        display_name="Operator 1",
        public_signing_key="sign-123",
        registered_at=datetime.now(),
        last_seen_at=datetime.now(),
        trust_state="trusted"
    )
    data = device.model_dump()
    assert data["device_id"] == "dev-1"
    assert "private_key" not in data

def test_encrypted_envelope_contains_no_keys():
    """Verify that EncryptedQuoteEnvelope carries ciphertext but no keys."""
    payload = EncryptedPayload(
        ciphertext="base64-data",
        nonce="base64-nonce",
        tag="base64-tag"
    )
    envelope = EncryptedQuoteEnvelope(
        quote_id="quote-1",
        encrypted_exact_location=payload
    )
    data = envelope.model_dump()
    
    assert data["quote_id"] == "quote-1"
    assert data["encrypted_exact_location"]["ciphertext"] == "base64-data"
    
    # Ensure no PRIVATE keys leaked into the envelope structure
    assert "private_key" not in str(data).lower()
    assert "secret" not in str(data).lower()

def test_docs_honesty():
    """Integration test: Check docs for overstrong claims about hosted isolation."""
    import os
    docs_path = os.path.join("docs", "proofs", "key_authority_boundary.md")
    with open(docs_path, "r") as f:
        content = f.read()
        
    # Should acknowledge the current dev state
    assert "Symmetric Bootstrap (Dev)" in content
    assert "The boundary is currently **procedural and architectural**, not yet cryptographic" in content
    assert "INTAKE_DEV_ENCRYPTION_KEY" in content
