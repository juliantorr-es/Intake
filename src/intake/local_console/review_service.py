"""Local service for reviewing and decrypting quotes."""

from typing import Any, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

from intake.sync.models import HostedQuoteProjection, EncryptedQuoteEnvelope
from intake.local_console.sync_client import LocalSyncClient
from intake.services.crypto_service import get_crypto_service, CryptoService
from intake.services.signing_service import LocalDeviceSigningService
from intake.config import get_settings

class LocalDecryptedQuoteReview(BaseModel):
    """Local-only model for a decrypted quote review."""
    quote_id: str
    status: str
    service_lane: str | None = None
    general_service_area: str | None = None
    created_at: datetime
    
    # Decrypted fields
    exact_location: str | None = None
    access_notes: str | None = None
    questionnaire_answers: dict[str, Any] | None = None
    decrypted_filenames: List[str] = Field(default_factory=list)

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
        # 1. We might want the projection first for metadata, 
        # but for this slice we'll just get the envelope.
        envelope = self.client.fetch_quote_envelope(quote_id)
        
        # 2. Decrypt fields
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

        filenames = []
        for enc_name in envelope.encrypted_uploads:
            filenames.append(self.crypto.decrypt_string(enc_name))

        # 3. Create the local-only review model
        # Note: We'd normally fetch the projection too to get the status/lane/etc.
        # but for simplicity we'll just return what we have.
        return LocalDecryptedQuoteReview(
            quote_id=quote_id,
            status="pending_local_review", # Placeholder
            created_at=datetime.now(), # Placeholder
            exact_location=exact_location,
            access_notes=access_notes,
            questionnaire_answers=questionnaire,
            decrypted_filenames=filenames
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
