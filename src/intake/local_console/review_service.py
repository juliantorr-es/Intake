"""Local service for reviewing and decrypting quotes."""

from typing import Any, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

from intake.sync.models import HostedQuoteProjection, EncryptedQuoteEnvelope
from intake.local_console.sync_client import LocalSyncClient
from intake.services.crypto_service import get_crypto_service, CryptoService
from intake.services.signing_service import LocalDeviceSigningService
from intake.config import get_settings
from intake.local_console.security.unlock import get_auth_window

class UploadEvidence(BaseModel):
    """Evidence of a file upload."""
    file_id: str
    original_filename: str | None = None
    content_type: str
    size_bytes: int
    sha256: str
    storage_provider: str
    stored_at: datetime

class LocalDecryptedQuoteReview(BaseModel):
    """Local-only model for a decrypted quote review."""
    quote_id: str
    status: str
    service_lane: str | None = None
    general_service_area: str | None = None
    created_at: datetime
    updated_at: datetime
    
    # Discovery metadata
    email_verified: bool = False
    upload_count: int = 0
    is_decrypted: bool = False
    is_locked: bool = True
    
    # Decrypted fields
    exact_location: str | None = None
    access_notes: str | None = None
    questionnaire_answers: dict[str, Any] | None = None
    
    # Evidence
    upload_evidence: List[UploadEvidence] = Field(default_factory=list)

class LocalQuoteReviewService:
    """Service for local-only quote review operations."""

    def __init__(
        self, 
        sync_client: LocalSyncClient | None = None,
        crypto_service: CryptoService | None = None,
        signing_service: LocalDeviceSigningService | None = None
    ):
        settings = get_settings()
        self.client = sync_client or LocalSyncClient()
        self.crypto = crypto_service or get_crypto_service()
        
        # Use existing signing key if available
        sign_key = settings.intake_local_signing_key.get_secret_value() if settings.intake_local_signing_key else None
        self.signer = signing_service or LocalDeviceSigningService(private_key_base64=sign_key)
        self.device_id = "dev-device-1" # In prod this would come from local identity storage

    def get_pending_reviews(self) -> List[HostedQuoteProjection]:
        """Get list of quotes pending review from hosted."""
        return self.client.fetch_pending_projections()

    def get_decrypted_review(self, quote_id: str) -> LocalDecryptedQuoteReview:
        """Fetch and decrypt a quote for local review."""
        # 1. Fetch projection for metadata
        projections = self.client.fetch_pending_projections()
        projection = next((p for p in projections if p.quote_id == quote_id), None)
        
        if not projection:
            # Fallback if not in pending list (might be already reviewed)
            # For v0 simplicity, we'll just raise 404 in the API handler
            raise ValueError(f"Quote {quote_id} not found in pending list")

        # 2. Fetch envelope for ciphertext
        envelope = self.client.fetch_quote_envelope(quote_id)
        
        # 3. Decrypt fields
        exact_location = None
        if envelope.encrypted_exact_location:
            decrypted = self.crypto.decrypt_json(envelope.encrypted_exact_location)
            exact_location = decrypted.get("location")

        access_notes = None
        if envelope.encrypted_access_notes:
            decrypted = self.crypto.decrypt_json(envelope.encrypted_access_notes)
            access_notes = decrypted.get("notes")

        questionnaire = None
        if envelope.encrypted_questionnaire:
            questionnaire = self.crypto.decrypt_json(envelope.encrypted_questionnaire)

        # 4. Populate evidence
        # In a real system, we'd fetch actual file records from the local receiver storage.
        # For this slice, we'll simulate evidence from the envelope and projection.
        evidence = []
        for i, enc_name in enumerate(envelope.encrypted_uploads):
            decrypted_name = self.crypto.decrypt_string(enc_name)
            evidence.append(UploadEvidence(
                file_id=f"file-{i}",
                original_filename=decrypted_name,
                content_type="image/jpeg", # Placeholder
                size_bytes=1024 * 500, # Placeholder
                sha256="sim-sha256-...",
                storage_provider="local_loopback_dev",
                stored_at=datetime.now()
            ))

        # 5. Check if we need to redact due to lock
        settings = get_settings()
        is_locked = False
        if settings.intake_require_local_unlock_for_decrypt:
            is_locked = not get_auth_window().is_unlocked

        if is_locked:
            # Redact sensitive fields
            exact_location = None
            access_notes = None
            questionnaire = None
            # Mask filenames in evidence
            for ev in evidence:
                ev.original_filename = "[LOCKED]"

        # 6. Create the local-only review model
        return LocalDecryptedQuoteReview(
            quote_id=quote_id,
            status=projection.status,
            service_lane=projection.service_lane,
            general_service_area=projection.general_service_area,
            created_at=projection.created_at,
            updated_at=projection.updated_at,
            email_verified=True, # Simulation
            upload_count=projection.upload_count,
            is_decrypted=not is_locked,
            is_locked=is_locked,
            exact_location=exact_location,
            access_notes=access_notes,
            questionnaire_answers=questionnaire,
            upload_evidence=evidence
        )

    def start_review(self, quote_id: str) -> dict:
        """Sign and push a QUOTE_REVIEW_START action to hosted."""
        envelope = self.signer.sign_action(
            device_id=self.device_id,
            action_kind="QUOTE_REVIEW_START",
            aggregate_type="QUOTE",
            aggregate_id=quote_id,
            payload={} # No extra payload needed for this action
        )
        return self.client.push_action(envelope)
