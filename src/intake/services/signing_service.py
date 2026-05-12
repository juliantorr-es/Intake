"""Service for local device signing and hosted verification."""

import base64
from datetime import datetime, timezone
from typing import Any
import uuid

from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.exceptions import InvalidSignature

from intake.sync.models import LocalDeviceActionEnvelope, HostedRegisteredDevice

class LocalDeviceSigningService:
    """Service for Local Console to sign actions."""
    
    def __init__(self, private_key_base64: str | None = None):
        if private_key_base64:
            self._private_key = ed25519.Ed25519PrivateKey.from_private_bytes(
                base64.b64decode(private_key_base64)
            )
        else:
            self._private_key = ed25519.Ed25519PrivateKey.generate()
            
    def get_private_key_base64(self) -> str:
        """Export private key for local storage (NEVER SEND TO HOSTED)."""
        return base64.b64encode(
            self._private_key.private_bytes_raw()
        ).decode("utf-8")
        
    def get_public_key_base64(self) -> str:
        """Export public key for registration on Hosted."""
        return base64.b64encode(
            self._private_key.public_key().public_bytes_raw()
        ).decode("utf-8")
        
    def sign_action(
        self, 
        device_id: str, 
        action_kind: str, 
        aggregate_type: str, 
        aggregate_id: str, 
        payload: dict[str, Any]
    ) -> LocalDeviceActionEnvelope:
        """Create and sign an action envelope."""
        action_id = str(uuid.uuid4())
        nonce = str(uuid.uuid4())
        issued_at = datetime.now(timezone.utc)
        
        # Create initial envelope without signature
        envelope = LocalDeviceActionEnvelope(
            action_id=action_id,
            device_id=device_id,
            action_kind=action_kind,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            issued_at=issued_at,
            nonce=nonce,
            payload=payload,
            signature="", # Placeholder
            signature_algorithm="ed25519"
        )
        
        # Sign canonical bytes
        canonical_bytes = envelope.get_canonical_payload()
        signature_bytes = self._private_key.sign(canonical_bytes)
        
        # Set signature
        envelope.signature = base64.b64encode(signature_bytes).decode("utf-8")
        return envelope


class HostedActionVerificationService:
    """Service for Hosted Intake to verify signed actions."""
    
    def __init__(self, sync_repo: Any | None = None, freshness_window_seconds: int = 300):
        from intake.storage.repositories import SyncRepository
        self.sync_repo = sync_repo or SyncRepository()
        self.freshness_window_seconds = freshness_window_seconds
        
    def verify_action(
        self, 
        envelope: LocalDeviceActionEnvelope, 
        registered_device: HostedRegisteredDevice
    ) -> bool:
        """Verify the signature and metadata of a signed action.
        
        Returns True if valid, raises ValueError/InvalidSignature if invalid.
        """
        # 1. Check device ID match
        if envelope.device_id != registered_device.device_id:
            raise ValueError("Device ID mismatch")
            
        # 2. Check trust state
        if registered_device.trust_state != "trusted":
            raise ValueError(f"Device is not trusted: {registered_device.trust_state}")
            
        # 3. Check freshness
        now = datetime.now(timezone.utc)
        delta = (now - envelope.issued_at).total_seconds()
        if abs(delta) > self.freshness_window_seconds:
            raise ValueError(f"Action is outside freshness window: {delta}s")
            
        # 4. Replay prevention (Action ID)
        if self.sync_repo.is_action_seen(envelope.action_id):
            raise ValueError(f"Duplicate action_id detected: {envelope.action_id}")
            
        # 5. Replay prevention (Nonce per device)
        if self.sync_repo.is_nonce_seen(envelope.device_id, envelope.nonce):
            raise ValueError(f"Duplicate nonce detected for device: {envelope.nonce}")
            
        # 6. Verify Signature
        if not registered_device.public_signing_key:
            raise ValueError("Registered device lacks public signing key")
            
        public_key = ed25519.Ed25519PublicKey.from_public_bytes(
            base64.b64decode(registered_device.public_signing_key)
        )
        
        signature_bytes = base64.b64decode(envelope.signature)
        canonical_bytes = envelope.get_canonical_payload()
        
        try:
            public_key.verify(signature_bytes, canonical_bytes)
        except InvalidSignature:
            raise ValueError("Invalid action signature")
            
        # Mark as seen if all checks pass
        self.sync_repo.track_action(envelope.action_id, envelope.device_id, envelope.issued_at)
        self.sync_repo.track_nonce(envelope.device_id, envelope.nonce, envelope.issued_at)
        
        return True
