"""Tests for synchronization protocol models."""

import pytest
from datetime import datetime
from intake.sync.models import (
    HostedQuoteProjection,
    EncryptedQuoteEnvelope,
    LocalOperatorAction
)


def test_quote_projection_serialization():
    """Test that quote projections can be serialized and deserialized."""
    now = datetime.now()
    projection = HostedQuoteProjection(
        quote_id="quote-123",
        status="submitted",
        service_lane="software_systems",
        general_service_area="San Francisco",
        created_at=now,
        updated_at=now,
        has_encrypted_payload=True,
        upload_count=2
    )
    
    data = projection.model_dump()
    assert data["quote_id"] == "quote-123"
    assert data["has_encrypted_payload"] is True
    
    # Round trip
    reconstructed = HostedQuoteProjection(**data)
    assert reconstructed.quote_id == projection.quote_id


def test_encrypted_envelope_serialization():
    """Test that encrypted envelopes hold ciphertext securely."""
    envelope = EncryptedQuoteEnvelope(
        quote_id="quote-123",
        ciphertext="SGVsbG8gV29ybGQ=", # Base64 "Hello World"
        nonce="nonce-123",
        tag="tag-123"
    )
    
    data = envelope.model_dump()
    assert data["ciphertext"] == "SGVsbG8gV29ybGQ="
    assert "tag" in data


def test_operator_action_serialization():
    """Test that operator actions can be captured."""
    action = LocalOperatorAction(
        action_id="action-456",
        quote_id="quote-123",
        action_type="approve",
        payload={"note": "Looks good"},
        signature="sig-123"
    )
    
    data = action.model_dump()
    assert data["action_type"] == "approve"
    assert data["payload"]["note"] == "Looks good"
    assert data["signature"] == "sig-123"


def test_redaction_boundary():
    """Test that a redacted projection does not contain sensitive fields."""
    now = datetime.now()
    projection = HostedQuoteProjection(
        quote_id="quote-123",
        status="submitted",
        created_at=now,
        updated_at=now,
        has_encrypted_payload=True,
        upload_count=0
    )
    
    data = projection.model_dump()
    # Ensure sensitive fields are NOT present in the projection
    assert "ciphertext" not in data
    assert "encrypted_payload" not in data
    assert "exact_location" not in data
