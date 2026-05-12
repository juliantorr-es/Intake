import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from intake.local_console.security.unlock import LocalAuthorizationWindow, reset_auth_window
from intake.local_console.review_service import LocalQuoteReviewService, LocalDecryptedQuoteReview
from intake.local_console.api.security import UnlockStatus

@pytest.fixture
def auth_window():
    reset_auth_window()
    return LocalAuthorizationWindow.get_instance()

def test_auth_window_expiry(auth_window):
    """Test that the auth window expires correctly."""
    auth_window.unlock()
    assert auth_window.is_unlocked == True
    
    # Mock time in the future
    auth_window._unlocked_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert auth_window.is_unlocked == False

def test_auth_window_manual_lock(auth_window):
    """Test that manual lock works."""
    auth_window.unlock()
    assert auth_window.is_unlocked == True
    auth_window.lock()
    assert auth_window.is_unlocked == False

def test_quote_redaction_when_locked(auth_window):
    """Test that sensitive fields are redacted when locked."""
    auth_window.lock()
    
    # Mock services
    mock_client = MagicMock()
    mock_crypto = MagicMock()
    
    # Mock projection
    from intake.sync.models import HostedQuoteProjection
    mock_client.fetch_pending_projections.return_value = [
        HostedQuoteProjection(
            quote_id="quote_1",
            status="submitted",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            upload_count=1
        )
    ]
    
    # Mock envelope
    from intake.sync.models import EncryptedQuoteEnvelope
    mock_client.fetch_quote_envelope.return_value = EncryptedQuoteEnvelope(
        quote_id="quote_1",
        encrypted_uploads=["encrypted_name"]
    )
    
    service = LocalQuoteReviewService(sync_client=mock_client, crypto_service=mock_crypto)
    
    review = service.get_decrypted_review("quote_1")
    
    assert review.is_locked == True
    assert review.exact_location is None
    assert review.upload_evidence[0].original_filename == "[LOCKED]"
    
    # Ensure crypto was NOT called
    assert mock_crypto.decrypt_json.call_count == 0

def test_quote_decryption_when_unlocked(auth_window):
    """Test that fields are decrypted when unlocked."""
    auth_window.unlock()
    
    mock_client = MagicMock()
    mock_crypto = MagicMock()
    mock_crypto.decrypt_json.return_value = {"location": "123 Main St"}
    mock_crypto.decrypt_string.return_value = "secret_file.pdf"
    
    from intake.sync.models import HostedQuoteProjection, EncryptedQuoteEnvelope
    mock_client.fetch_pending_projections.return_value = [
        HostedQuoteProjection(
            quote_id="quote_1",
            status="submitted",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            upload_count=1
        )
    ]
    mock_client.fetch_quote_envelope.return_value = EncryptedQuoteEnvelope(
        quote_id="quote_1",
        encrypted_exact_location="encrypted_loc",
        encrypted_uploads=["encrypted_name"]
    )
    
    service = LocalQuoteReviewService(sync_client=mock_client, crypto_service=mock_crypto)
    review = service.get_decrypted_review("quote_1")
    
    assert review.is_locked == False
    assert review.exact_location == "123 Main St"
    assert review.upload_evidence[0].original_filename == "secret_file.pdf"
    
    # Ensure crypto WAS called
    assert mock_crypto.decrypt_json.call_count > 0
