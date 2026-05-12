from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from intake.local_console.app import app
from intake.local_console.review_service import LocalDecryptedQuoteReview, UploadEvidence

client = TestClient(app)

def test_health_check():
    response = client.get("/api/local/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_status_endpoint_redaction():
    response = client.get("/api/local/status")
    assert response.status_code == 200
    data = response.json()

    # Ensure sensitive settings are not leaked as raw values
    # (The API returns boolean flags, not the keys themselves)
    assert "hosted_url" in data
    assert "sync_auth_configured" in data
    assert isinstance(data["sync_auth_configured"], bool)
    assert "encryption_key_configured" in data
    assert isinstance(data["encryption_key_configured"], bool)

def test_quote_review_model_redaction():
    # Verify that the model doesn't include raw keys
    review = LocalDecryptedQuoteReview(
        quote_id="q_123",
        status="submitted",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        is_decrypted=True,
        exact_location="123 Main St",
        upload_evidence=[
            UploadEvidence(
                file_id="f_1",
                original_filename="secret.jpg",
                content_type="image/jpeg",
                size_bytes=100,
                sha256="abc",
                storage_provider="local",
                stored_at=datetime.now()
            )
        ]
    )

    data = review.model_dump()
    # Ensure no secret fields were added accidentally
    allowed_keys = {
        "quote_id", "status", "service_lane", "general_service_area",
        "created_at", "updated_at", "email_verified", "upload_count",
        "is_decrypted", "is_locked", "exact_location", "access_notes",
        "questionnaire_answers", "upload_evidence"
    }
    assert set(data.keys()).issubset(allowed_keys)

    # Ensure evidence doesn't have local paths
    for ev in data["upload_evidence"]:
        assert "storage_ref" not in ev
        assert "local_path" not in ev

@pytest.fixture(autouse=True)
def setup_settings():
    from pydantic import SecretStr

    from intake.config import get_settings, reset_settings
    from intake.services.signing_service import LocalDeviceSigningService
    settings = get_settings()
    # Generate a real Ed25519 key string
    signer = LocalDeviceSigningService()
    settings.intake_local_signing_key = SecretStr(signer.get_private_key_base64())
    yield
    reset_settings()

def test_get_quotes_pending_api(monkeypatch):
    # Mock the service to avoid network calls
    from intake.local_console.review_service import LocalQuoteReviewService
    from intake.sync.models import HostedQuoteProjection

    def mock_get_pending(self):
        return [
            HostedQuoteProjection(
                quote_id="q_1",
                status="submitted",
                created_at=datetime.now(),
                updated_at=datetime.now(),
                has_encrypted_payload=True,
                upload_count=1,
                email_verified=True,
                decrypted=True
            )
        ]

    monkeypatch.setattr(LocalQuoteReviewService, "get_pending_reviews", mock_get_pending)

    response = client.get("/api/local/quotes/pending")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["quote_id"] == "q_1"
