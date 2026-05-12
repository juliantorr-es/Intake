"""Tests for signed local device actions and verification."""

import pytest
import base64
from datetime import datetime, timedelta, timezone
from intake.services.signing_service import LocalDeviceSigningService, HostedActionVerificationService
from intake.sync.models import HostedRegisteredDevice

def test_keypair_generation():
    """Verify that we can generate and export keys."""
    service = LocalDeviceSigningService()
    priv = service.get_private_key_base64()
    pub = service.get_public_key_base64()
    
    assert len(priv) > 0
    assert len(pub) > 0
    
    # Reload from private key
    service2 = LocalDeviceSigningService(private_key_base64=priv)
    assert service2.get_public_key_base64() == pub

def test_sign_and_verify_success():
    """Verify standard sign and verify loop."""
    signing_service = LocalDeviceSigningService()
    verify_service = HostedActionVerificationService()
    
    device_id = "test-device-1"
    pub_key = signing_service.get_public_key_base64()
    
    registered_device = HostedRegisteredDevice(
        device_id=device_id,
        display_name="Test Device",
        public_signing_key=pub_key,
        registered_at=datetime.now(timezone.utc),
        last_seen_at=datetime.now(timezone.utc),
        trust_state="trusted"
    )
    
    envelope = signing_service.sign_action(
        device_id=device_id,
        action_kind="test_action",
        aggregate_type="QUOTE",
        aggregate_id="quote-123",
        payload={"foo": "bar"}
    )
    
    assert verify_service.verify_action(envelope, registered_device) is True

def test_tampered_payload_fails():
    """Verify that tampering with the payload invalidates the signature."""
    signing_service = LocalDeviceSigningService()
    verify_service = HostedActionVerificationService()
    
    device_id = "test-device-1"
    registered_device = HostedRegisteredDevice(
        device_id=device_id,
        display_name="Test Device",
        public_signing_key=signing_service.get_public_key_base64(),
        registered_at=datetime.now(timezone.utc),
        last_seen_at=datetime.now(timezone.utc),
        trust_state="trusted"
    )
    
    envelope = signing_service.sign_action(
        device_id=device_id,
        action_kind="test_action",
        aggregate_type="QUOTE",
        aggregate_id="quote-123",
        payload={"foo": "bar"}
    )
    
    # Tamper
    envelope.payload["foo"] = "tampered"
    
    assert verify_service.verify_action(envelope, registered_device) is False

def test_tampered_metadata_fails():
    """Verify that tampering with metadata invalidates the signature."""
    signing_service = LocalDeviceSigningService()
    verify_service = HostedActionVerificationService()
    
    device_id = "test-device-1"
    registered_device = HostedRegisteredDevice(
        device_id=device_id,
        display_name="Test Device",
        public_signing_key=signing_service.get_public_key_base64(),
        registered_at=datetime.now(timezone.utc),
        last_seen_at=datetime.now(timezone.utc),
        trust_state="trusted"
    )
    
    envelope = signing_service.sign_action(
        device_id=device_id,
        action_kind="test_action",
        aggregate_type="QUOTE",
        aggregate_id="quote-123",
        payload={"foo": "bar"}
    )
    
    # Tamper metadata
    envelope.action_kind = "malicious_action"
    
    assert verify_service.verify_action(envelope, registered_device) is False

def test_wrong_device_key_fails():
    """Verify that a signature from a different device is rejected."""
    service_a = LocalDeviceSigningService()
    service_b = LocalDeviceSigningService()
    verify_service = HostedActionVerificationService()
    
    device_id = "device-a"
    registered_device_a = HostedRegisteredDevice(
        device_id=device_id,
        display_name="Device A",
        public_signing_key=service_a.get_public_key_base64(),
        registered_at=datetime.now(timezone.utc),
        last_seen_at=datetime.now(timezone.utc),
        trust_state="trusted"
    )
    
    # Sign with device B but claim it's from device A
    envelope = service_b.sign_action(
        device_id=device_id,
        action_kind="test_action",
        aggregate_type="QUOTE",
        aggregate_id="quote-123",
        payload={}
    )
    
    assert verify_service.verify_action(envelope, registered_device_a) is False

def test_replay_prevention_action_id():
    """Verify that replaying the same action_id is rejected."""
    signing_service = LocalDeviceSigningService()
    verify_service = HostedActionVerificationService()
    
    device_id = "test-device-1"
    registered_device = HostedRegisteredDevice(
        device_id=device_id,
        display_name="Test Device",
        public_signing_key=signing_service.get_public_key_base64(),
        registered_at=datetime.now(timezone.utc),
        last_seen_at=datetime.now(timezone.utc),
        trust_state="trusted"
    )
    
    envelope = signing_service.sign_action(
        device_id=device_id,
        action_kind="test_action",
        aggregate_type="QUOTE",
        aggregate_id="q1",
        payload={}
    )
    
    assert verify_service.verify_action(envelope, registered_device) is True
    
    # Replay
    with pytest.raises(ValueError, match="Duplicate action_id"):
        verify_service.verify_action(envelope, registered_device)

def test_replay_prevention_nonce():
    """Verify that replaying a nonce for the same device is rejected."""
    signing_service = LocalDeviceSigningService()
    verify_service = HostedActionVerificationService()
    
    device_id = "test-device-1"
    registered_device = HostedRegisteredDevice(
        device_id=device_id,
        display_name="Test Device",
        public_signing_key=signing_service.get_public_key_base64(),
        registered_at=datetime.now(timezone.utc),
        last_seen_at=datetime.now(timezone.utc),
        trust_state="trusted"
    )
    
    e1 = signing_service.sign_action(device_id, "a1", "Q", "q1", {})
    assert verify_service.verify_action(e1, registered_device) is True
    
    # Duplicate nonce manually
    e2 = signing_service.sign_action(device_id, "a2", "Q", "q2", {})
    e2.nonce = e1.nonce
    # Re-sign to make signature valid for the duplicate nonce
    canonical = e2.get_canonical_payload()
    sig = signing_service._private_key.sign(canonical)
    e2.signature = base64.b64encode(sig).decode("utf-8")
    
    with pytest.raises(ValueError, match="Duplicate nonce"):
        verify_service.verify_action(e2, registered_device)

def test_freshness_check():
    """Verify that stale actions are rejected."""
    signing_service = LocalDeviceSigningService()
    verify_service = HostedActionVerificationService(freshness_window_seconds=60)
    
    device_id = "test-device-1"
    registered_device = HostedRegisteredDevice(
        device_id=device_id,
        display_name="Test Device",
        public_signing_key=signing_service.get_public_key_base64(),
        registered_at=datetime.now(timezone.utc),
        last_seen_at=datetime.now(timezone.utc),
        trust_state="trusted"
    )
    
    envelope = signing_service.sign_action(device_id, "a1", "Q", "q1", {})
    
    # Set to 10 minutes ago
    envelope.issued_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    # Re-sign
    canonical = envelope.get_canonical_payload()
    sig = signing_service._private_key.sign(canonical)
    envelope.signature = base64.b64encode(sig).decode("utf-8")
    
    with pytest.raises(ValueError, match="outside freshness window"):
        verify_service.verify_action(envelope, registered_device)
