import pytest
import os
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch
from fastapi import UploadFile, HTTPException
from intake.services.upload_service import UploadService
from intake.domain.quotes import Quote, QuoteStatus, UploadStatus, Upload
from intake.domain.crypto import EncryptedPayload

@pytest.fixture
def temp_upload_root(tmp_path):
    root = tmp_path / "uploads"
    root.mkdir()
    yield root
    if root.exists():
        shutil.rmtree(root)

@pytest.fixture
def mock_repos():
    return {
        "quote": MagicMock(),
        "account": MagicMock(),
        "event": MagicMock(),
    }

@pytest.fixture
def upload_service(mock_repos, temp_upload_root):
    from intake.services.storage_service import StorageService
    from intake.services.upload_validation_service import UploadValidationService
    
    storage = StorageService(upload_root=temp_upload_root)
    validation = UploadValidationService()
    crypto = MagicMock()
    crypto.encrypt_string.return_value = EncryptedPayload(
        ciphertext="encrypted", nonce="nonce", tag="tag"
    )
    
    # Mock verified account by default
    from intake.domain.accounts import Account
    from datetime import datetime
    mock_account = Account(id="user-1", email_verified_at=datetime.now())
    mock_repos["account"].get_by_id.return_value = mock_account
    
    return UploadService(
        quote_repo=mock_repos["quote"],
        account_repo=mock_repos["account"],
        event_repo=mock_repos["event"],
        crypto_service=crypto,
        storage_service=storage,
        validation_service=validation
    )

def test_upload_ownership_check(upload_service, mock_repos):
    # Mock quote owned by another user
    mock_quote = Quote(id="quote-1", account_id="other-user", status=QuoteStatus.DRAFT)
    mock_repos["quote"].get_by_id.return_value = mock_quote
    
    mock_file = MagicMock()
    
    with pytest.raises(HTTPException) as excinfo:
        upload_service.handle_upload("user-1", "quote-1", mock_file)
    
    assert excinfo.value.status_code == 403
    assert "Not authorized" in excinfo.value.detail

def test_upload_email_verification_check(upload_service, mock_repos):
    # Mock quote owned by user but account not verified
    mock_quote = Quote(id="quote-1", account_id="user-1", status=QuoteStatus.DRAFT)
    mock_repos["quote"].get_by_id.return_value = mock_quote
    
    from intake.domain.accounts import Account
    mock_account = Account(id="user-1", email_verified_at=None)
    mock_repos["account"].get_by_id.return_value = mock_account
    
    mock_file = MagicMock()
    
    with pytest.raises(HTTPException) as excinfo:
        upload_service.handle_upload("user-1", "quote-1", mock_file)
    
    assert excinfo.value.status_code == 403
    assert "Email verification required" in excinfo.value.detail

def test_upload_quote_status_check(upload_service, mock_repos):
    # Mock quote in immutable state
    mock_quote = Quote(id="quote-1", account_id="user-1", status=QuoteStatus.ACCEPTED)
    mock_repos["quote"].get_by_id.return_value = mock_quote
    
    mock_file = MagicMock()
    
    with pytest.raises(HTTPException) as excinfo:
        upload_service.handle_upload("user-1", "quote-1", mock_file)
    
    assert excinfo.value.status_code == 400
    assert "does not allow uploads" in excinfo.value.detail

def test_upload_file_size_limit(upload_service, mock_repos):
    mock_quote = Quote(id="quote-1", account_id="user-1", status=QuoteStatus.DRAFT)
    mock_repos["quote"].get_by_id.return_value = mock_quote
    
    mock_file = MagicMock()
    mock_file.filename = "test.jpg"
    mock_file.content_type = "image/jpeg"
    # 20MB is over the 15MB limit for images
    content = b"a" * (20 * 1024 * 1024)
    mock_file.file.read.return_value = content
    
    with pytest.raises(HTTPException) as excinfo:
        upload_service.handle_upload("user-1", "quote-1", mock_file)
    
    assert excinfo.value.status_code == 400
    assert "exceeds maximum size" in excinfo.value.detail

def test_upload_invalid_extension(upload_service, mock_repos):
    mock_quote = Quote(id="quote-1", account_id="user-1", status=QuoteStatus.DRAFT)
    mock_repos["quote"].get_by_id.return_value = mock_quote
    
    mock_file = MagicMock()
    mock_file.filename = "test.exe"
    mock_file.content_type = "application/octet-stream"
    mock_file.file.read.return_value = b"bytes"
    
    with pytest.raises(HTTPException) as excinfo:
        upload_service.handle_upload("user-1", "quote-1", mock_file)
    
    assert excinfo.value.status_code == 400
    assert "Disallowed file extension" in excinfo.value.detail

def test_successful_upload(upload_service, mock_repos, temp_upload_root):
    mock_quote = Quote(id="quote-1", account_id="user-1", status=QuoteStatus.DRAFT)
    mock_repos["quote"].get_by_id.return_value = mock_quote
    
    mock_file = MagicMock()
    mock_file.filename = "test.jpg"
    mock_file.content_type = "image/jpeg"
    content = b"fake-image-bytes"
    mock_file.file.read.return_value = content
    
    upload = upload_service.handle_upload("user-1", "quote-1", mock_file)
    
    # Verify persistence
    mock_repos["quote"].add_upload.assert_called_once()
    mock_repos["event"].append.assert_called_once()
    
    # Verify domain model
    assert upload.extension == ".jpg"
    assert upload.size_bytes == len(content)
    assert upload.status == UploadStatus.ACCEPTED
    
    # Verify storage
    file_path = temp_upload_root / upload.storage_relative_path
    assert file_path.exists()
    assert file_path.read_bytes() == content
    # Verify filename is random and not the original
    assert "test.jpg" not in file_path.name

def test_path_traversal_prevention(upload_service, mock_repos, temp_upload_root):
    mock_quote = Quote(id="quote-1", account_id="user-1", status=QuoteStatus.DRAFT)
    mock_repos["quote"].get_by_id.return_value = mock_quote
    
    mock_file = MagicMock()
    mock_file.filename = "../../../etc/passwd.jpg"
    mock_file.content_type = "image/jpeg"
    mock_file.file.read.return_value = b"bytes"
    
    upload = upload_service.handle_upload("user-1", "quote-1", mock_file)
    
    # Should still work but the path should be safe
    assert ".." not in upload.storage_relative_path
    file_path = temp_upload_root / upload.storage_relative_path
    assert str(file_path.absolute()).startswith(str(temp_upload_root.absolute()))

def test_mime_type_mismatch_rejection(upload_service, mock_repos):
    mock_quote = Quote(id="quote-1", account_id="user-1", status=QuoteStatus.DRAFT)
    mock_repos["quote"].get_by_id.return_value = mock_quote
    
    mock_file = MagicMock()
    mock_file.filename = "test.jpg"
    mock_file.content_type = "application/pdf" # Mismatch
    mock_file.file.read.return_value = b"bytes"
    
    with pytest.raises(HTTPException) as excinfo:
        upload_service.handle_upload("user-1", "quote-1", mock_file)
    
    assert excinfo.value.status_code == 400
    assert "MIME type mismatch" in excinfo.value.detail
