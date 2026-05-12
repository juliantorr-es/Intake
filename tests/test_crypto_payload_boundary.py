"""Tests for sensitive payload encryption and boundary enforcement."""

import pytest
import json
from intake.services.quote_service import QuoteService
from intake.services.upload_service import UploadService
from intake.services.crypto_service import CryptoService
from intake.domain.quotes import Quote, QuoteStatus, QuoteServiceLane, UploadStatus
from intake.domain.crypto import EncryptedPayload
from intake.storage.repositories import QuoteRepository
from unittest.mock import MagicMock
from fastapi import UploadFile

@pytest.fixture
def crypto_service():
    # Use a fixed key for testing
    key = CryptoService.generate_local_dev_key()
    import base64
    from intake.config import get_settings
    settings = get_settings()
    settings.intake_dev_encryption_key = base64.urlsafe_b64decode(key) # This might not work if it expects SecretStr
    
    # Actually just create the service directly
    return CryptoService(encryption_key=base64.urlsafe_b64decode(key))

@pytest.fixture
def mock_repos():
    return {
        "quote": MagicMock(),
        "account": MagicMock(),
        "event": MagicMock(),
    }

def test_exact_location_encryption(crypto_service, mock_repos):
    """Prove that exact location is encrypted and plaintext is hidden."""
    service = QuoteService(
        repo=mock_repos["quote"],
        crypto_service=crypto_service,
        event_log=MagicMock()
    )
    
    mock_quote = Quote(id="quote-1", status=QuoteStatus.DRAFT)
    mock_repos["quote"].get_by_id.return_value = mock_quote
    mock_repos["quote"].update.side_effect = lambda q: q
    
    # Add location
    plaintext_location = "123 Secret Street, Nowhere"
    updated = service.add_location(
        quote_id="quote-1",
        general_service_area="Nowhere",
        exact_location=plaintext_location
    )
    
    # 1. Verify EncryptedPayload object exists
    assert isinstance(updated.encrypted_exact_location, EncryptedPayload)
    
    # 2. Verify plaintext is NOT in the ciphertext (base64 check)
    assert plaintext_location not in updated.encrypted_exact_location.ciphertext
    
    # 3. Verify decryption works
    decrypted = crypto_service.decrypt_json(updated.encrypted_exact_location)
    assert decrypted["location"] == plaintext_location
    
    # 4. Verify no 'enc:' prefix (old mock system)
    assert not updated.encrypted_exact_location.ciphertext.startswith("enc:")

def test_questionnaire_encryption(crypto_service, mock_repos):
    """Prove that questionnaire answers are encrypted."""
    service = QuoteService(
        repo=mock_repos["quote"],
        crypto_service=crypto_service,
        event_log=MagicMock()
    )
    
    mock_quote = Quote(id="quote-1", status=QuoteStatus.DRAFT)
    mock_repos["quote"].get_by_id.return_value = mock_quote
    mock_repos["quote"].update.side_effect = lambda q: q
    
    answers = {"sq_ft": 2500, "rooms": 4, "secret_code": "ALPHA-9"}
    updated = service.add_questionnaire(quote_id="quote-1", answers=answers)
    
    assert isinstance(updated.encrypted_questionnaire, EncryptedPayload)
    
    # Verify decryption
    decrypted = crypto_service.decrypt_json(updated.encrypted_questionnaire)
    assert decrypted == answers
    assert decrypted["secret_code"] == "ALPHA-9"

def test_upload_filename_encryption(crypto_service, mock_repos):
    """Prove that original filenames are encrypted in uploads."""
    # We need to mock more for handle_upload
    from intake.services.storage_service import StorageService
    from intake.services.upload_validation_service import UploadValidationService
    
    storage = MagicMock()
    storage.store_file.return_value = ("obj-1", "path/to/file")
    validation = UploadValidationService()
    
    # Mock account
    from intake.domain.accounts import Account
    from datetime import datetime
    mock_account = Account(id="user-1", email_verified_at=datetime.now())
    mock_repos["account"].get_by_id.return_value = mock_account
    
    service = UploadService(
        quote_repo=mock_repos["quote"],
        account_repo=mock_repos["account"],
        event_repo=mock_repos["event"],
        crypto_service=crypto_service,
        storage_service=storage,
        validation_service=validation
    )
    
    mock_quote = Quote(id="quote-1", account_id="user-1", status=QuoteStatus.DRAFT)
    mock_repos["quote"].get_by_id.return_value = mock_quote
    
    mock_file = MagicMock()
    mock_file.filename = "sensitive_blueprint.pdf"
    mock_file.content_type = "application/pdf"
    mock_file.file.read.return_value = b"fake-pdf-content"
    
    upload = service.handle_upload("user-1", "quote-1", mock_file)
    
    # Verify original filename is encrypted
    assert isinstance(upload.encrypted_original_filename, EncryptedPayload)
    assert "sensitive_blueprint" not in upload.encrypted_original_filename.ciphertext
    
    # Verify decryption
    decrypted_filename = crypto_service.decrypt_string(upload.encrypted_original_filename)
    assert decrypted_filename == "sensitive_blueprint.pdf"

def test_public_redaction_consistency(mock_repos):
    """Verify that SafeQuoteSummary and get_safe_summary redact everything sensitive."""
    from intake.domain.crypto import EncryptedPayload
    
    quote = Quote(
        id="quote-1",
        short_summary="A safe summary",
        general_service_area="Public Area",
        encrypted_exact_location=EncryptedPayload(ciphertext="abc", nonce="123"),
        encrypted_access_notes=EncryptedPayload(ciphertext="def", nonce="456"),
        encrypted_questionnaire=EncryptedPayload(ciphertext="ghi", nonce="789"),
    )
    
    summary = quote.get_safe_summary()
    
    # Safe fields
    assert summary["short_summary"] == "A safe summary"
    assert summary["general_service_area"] == "Public Area"
    
    # Sensitive fields must be ABSENT
    assert "encrypted_exact_location" not in summary
    assert "encrypted_access_notes" not in summary
    assert "encrypted_questionnaire" not in summary
    assert "exact_location" not in summary
    
    # String representation check
    summary_str = json.dumps(summary)
    assert "abc" not in summary_str
    assert "123" not in summary_str
