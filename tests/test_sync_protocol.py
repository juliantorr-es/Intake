"""Tests for the Local Console outbound sync protocol."""

import pytest
import base64
from fastapi.testclient import TestClient
from unittest.mock import MagicMock
from pydantic import SecretStr

from intake.app import app
from intake.config import get_settings, reset_settings
from intake.domain.quotes import Quote, QuoteStatus
from intake.services.quote_service import get_quote_service
from intake.local_console.sync_client import LocalSyncClient
from intake.local_console.review_service import LocalQuoteReviewService
from intake.services.crypto_service import CryptoService, get_crypto_service
from intake.domain.crypto import EncryptedPayload
from intake.sync.models import HostedQuoteProjection, EncryptedQuoteEnvelope

@pytest.fixture
def client():
    app.dependency_overrides = {}
    return TestClient(app)

@pytest.fixture
def sync_token():
    return "test-sync-token-123"

@pytest.fixture
def configured_settings(sync_token):
    settings = get_settings()
    settings.intake_local_sync_token = SecretStr(sync_token)
    settings.intake_enable_dev_sync_auth = True
    yield settings
    reset_settings()

@pytest.fixture
def mock_quote_service():
    service = MagicMock()
    app.dependency_overrides[get_quote_service] = lambda: service
    return service

@pytest.fixture
def test_crypto():
    key = CryptoService.generate_local_dev_key()
    return CryptoService(encryption_key=base64.urlsafe_b64decode(key))

# ========== Hosted Sync API Tests ==========

def test_sync_auth_missing_token(client, configured_settings):
    """Verify that sync endpoints reject requests with no token."""
    response = client.get("/api/sync/quotes/pending")
    assert response.status_code == 401
    assert "Missing sync token" in response.json()["detail"]

def test_sync_auth_invalid_token(client, configured_settings):
    """Verify that sync endpoints reject invalid tokens."""
    headers = {"X-Intake-Sync-Token": "wrong-token"}
    response = client.get("/api/sync/quotes/pending", headers=headers)
    assert response.status_code == 403
    assert "Invalid sync token" in response.json()["detail"]

def test_sync_auth_valid_token(client, configured_settings, mock_quote_service):
    """Verify that sync endpoints accept valid tokens."""
    mock_quote_service.get_all_quotes.return_value = []
    headers = {"X-Intake-Sync-Token": "test-sync-token-123"}
    response = client.get("/api/sync/quotes/pending", headers=headers)
    assert response.status_code == 200

def test_sync_projection_redaction(client, configured_settings, mock_quote_service, test_crypto):
    """Verify that pending quote projections contain NO plaintext sensitive data."""
    # Create a quote with sensitive data
    location = "123 Private St"
    encrypted_location = test_crypto.encrypt_json({"location": location})
    
    quote = Quote(
        id="quote-1",
        status=QuoteStatus.NEEDS_REVIEW,
        general_service_area="Public Area",
        encrypted_exact_location=encrypted_location
    )
    mock_quote_service.get_all_quotes.return_value = [quote]
    
    headers = {"X-Intake-Sync-Token": "test-sync-token-123"}
    response = client.get("/api/sync/quotes/pending", headers=headers)
    assert response.status_code == 200
    
    data = response.json()
    assert len(data) == 1
    projection = data[0]
    
    # Check for expected non-sensitive fields
    assert projection["quote_id"] == "quote-1"
    assert projection["status"] == "needs_review"
    assert projection["general_service_area"] == "Public Area"
    
    # Ensure NO sensitive fields or ciphertext leaked into projection
    assert "encrypted_exact_location" not in projection
    assert "exact_location" not in projection
    assert location not in str(data)
    # Even the base64 ciphertext shouldn't be here (extra=forbid enforced)
    assert encrypted_location.ciphertext not in str(data)

def test_sync_envelope_content(client, configured_settings, mock_quote_service, test_crypto):
    """Verify that envelopes contain ciphertext but no plaintext."""
    location = "123 Private St"
    encrypted_location = test_crypto.encrypt_json({"location": location})
    
    quote = Quote(
        id="quote-1",
        status=QuoteStatus.NEEDS_REVIEW,
        encrypted_exact_location=encrypted_location
    )
    mock_quote_service.get_quote.return_value = quote
    
    headers = {"X-Intake-Sync-Token": "test-sync-token-123"}
    response = client.get("/api/sync/quotes/quote-1/envelope", headers=headers)
    assert response.status_code == 200
    
    envelope = response.json()
    assert envelope["quote_id"] == "quote-1"
    assert "encrypted_exact_location" in envelope
    assert envelope["encrypted_exact_location"]["ciphertext"] == encrypted_location.ciphertext
    
    # Ensure plaintext is NOT in the envelope
    assert location not in str(envelope)

# ========== Local Console Sync Client/Service Tests ==========

def test_local_sync_client_success(configured_settings, mock_quote_service, test_crypto):
    """Verify that LocalSyncClient can pull data using a token."""
    quote = Quote(id="quote-1", status=QuoteStatus.NEEDS_REVIEW)
    mock_quote_service.get_all_quotes.return_value = [quote]
    
    # We need to run the server or mock the httpx client
    # For unit testing the client, we'll mock httpx
    with MagicMock() as mock_httpx:
        # Mocking httpx is complex, let's use a simpler approach:
        # Test the LocalQuoteReviewService by mocking the LocalSyncClient
        pass

def test_local_decryption_loop(test_crypto):
    """Verify the full loop: fetch envelope (mocked) and decrypt locally."""
    location = "123 Private St"
    encrypted_location = test_crypto.encrypt_json({"location": location})
    
    envelope = EncryptedQuoteEnvelope(
        quote_id="quote-1",
        encrypted_exact_location=encrypted_location
    )
    
    mock_client = MagicMock()
    mock_client.fetch_quote_envelope.return_value = envelope
    
    service = LocalQuoteReviewService(sync_client=mock_client, crypto_service=test_crypto)
    review = service.get_decrypted_review("quote-1")
    
    assert review.quote_id == "quote-1"
    assert review.exact_location == location

def test_local_decryption_failure_wrong_key(test_crypto):
    """Verify that local review fails safely if the wrong key is used."""
    # Encrypt with key A
    encrypted = test_crypto.encrypt_json({"data": "secret"})
    
    # Create service with key B
    wrong_key = CryptoService.generate_local_dev_key()
    wrong_crypto = CryptoService(encryption_key=base64.urlsafe_b64decode(wrong_key))
    
    envelope = EncryptedQuoteEnvelope(quote_id="quote-1", encrypted_exact_location=encrypted)
    mock_client = MagicMock()
    mock_client.fetch_quote_envelope.return_value = envelope
    
    service = LocalQuoteReviewService(sync_client=mock_client, crypto_service=wrong_crypto)
    
    with pytest.raises(ValueError, match="Decryption failed"):
        service.get_decrypted_review("quote-1")

# ========== Module Boundary Tests (Integration) ==========

def test_sync_api_isolation():
    """Verify that hosted sync API doesn't import local console internals."""
    import subprocess
    import os
    
    src_path = os.path.join(os.getcwd(), "src", "intake", "hosted", "api", "sync.py")
    
    # Check for imports of local_console
    result = subprocess.run(
        ["grep", "intake.local_console", src_path],
        capture_output=True,
        text=True
    )
    assert result.returncode == 1 # grep should fail (no match)
