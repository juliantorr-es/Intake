"""Tests for email verification flow."""

import pytest
from datetime import timedelta
from unittest.mock import MagicMock

from intake.domain.accounts import Account, EmailVerificationCode
from intake.domain.time import utc_now
from intake.services.email_verification_service import EmailVerificationService
from intake.storage.repositories import AccountRepository, EmailVerificationRepository


@pytest.fixture
def mock_account_repo():
    return MagicMock(spec=AccountRepository)


@pytest.fixture
def mock_verification_repo():
    return MagicMock(spec=EmailVerificationRepository)


@pytest.fixture
def mock_email_sender():
    return MagicMock()


@pytest.fixture
def mock_crypto_service():
    service = MagicMock()
    service.encrypt_json.return_value = MagicMock(ciphertext="enc:email", nonce="nonce")
    return service


@pytest.fixture
def service(mock_account_repo, mock_verification_repo, mock_email_sender, mock_crypto_service):
    return EmailVerificationService(
        account_repo=mock_account_repo,
        verification_repo=mock_verification_repo,
        email_sender=mock_email_sender,
        crypto_service=mock_crypto_service,
        event_log=MagicMock()
    )


def test_normalize_email(service):
    """Test email normalization."""
    assert service._normalize_email("  User@Example.com  ") == "user@example.com"


def test_hash_email_is_deterministic(service):
    """Test that email hash is deterministic."""
    email = "test@example.com"
    h1 = service._hash_email(email)
    h2 = service._hash_email(email)
    assert h1 == h2
    assert len(h1) == 64 # SHA-256 hex


def test_start_verification_creates_records(service, mock_account_repo, mock_verification_repo, mock_email_sender):
    """Test starting verification creates DB records and sends email."""
    account_id = "user-1"
    email = "test@example.com"
    
    mock_account = Account(id=account_id)
    mock_account_repo.get_by_id.return_value = mock_account
    mock_account_repo.get_by_email_hash.return_value = None
    
    success = service.start_verification(account_id, email)
    
    assert success is True
    # Verify account update
    mock_account_repo.update.assert_called_once()
    updated_account = mock_account_repo.update.call_args[0][0]
    assert updated_account.normalized_email_hash is not None
    
    # Verify verification code creation
    mock_verification_repo.create.assert_called_once()
    
    # Verify email sent
    mock_email_sender.send_verification_email.assert_called_once()
    sent_email, sent_code = mock_email_sender.send_verification_email.call_args[0]
    assert sent_email == "test@example.com"
    assert len(sent_code) == 6


def test_verify_code_success(service, mock_account_repo, mock_verification_repo):
    """Test successful code verification."""
    account_id = "user-1"
    email = "test@example.com"
    code_raw = "123456"
    code_hash = service._hash_code(code_raw)
    email_hash = service._hash_email(email)
    
    mock_account = Account(id=account_id, normalized_email_hash=email_hash)
    mock_account_repo.get_by_id.return_value = mock_account
    
    v_code = EmailVerificationCode(
        account_id=account_id,
        email_hash=email_hash,
        code_hash=code_hash,
        expires_at=utc_now() + timedelta(minutes=15)
    )
    mock_verification_repo.get_active_by_email_hash.return_value = [v_code]
    
    success = service.verify_code(account_id, email, code_raw)
    
    assert success is True
    assert v_code.consumed_at is not None
    mock_account_repo.update.assert_called_once()
    assert mock_account.email_verified_at is not None


def test_verify_code_wrong_code(service, mock_verification_repo):
    """Test verification with wrong code."""
    account_id = "user-1"
    email = "test@example.com"
    email_hash = service._hash_email(email)
    
    v_code = EmailVerificationCode(
        account_id=account_id,
        email_hash=email_hash,
        code_hash="different-hash",
        expires_at=utc_now() + timedelta(minutes=15)
    )
    mock_verification_repo.get_active_by_email_hash.return_value = [v_code]
    
    success = service.verify_code(account_id, email, "123456")
    
    assert success is False
    assert v_code.attempts == 1
    mock_verification_repo.update.assert_called_once_with(v_code)


def test_verify_code_expired(service, mock_verification_repo):
    """Test verification with expired code."""
    account_id = "user-1"
    email = "test@example.com"
    code_raw = "123456"
    code_hash = service._hash_code(code_raw)
    email_hash = service._hash_email(email)
    
    v_code = EmailVerificationCode(
        account_id=account_id,
        email_hash=email_hash,
        code_hash=code_hash,
        expires_at=utc_now() - timedelta(minutes=1) # Expired
    )
    mock_verification_repo.get_active_by_email_hash.return_value = [v_code]
    
    # get_active_by_email_hash should usually not return expired codes, 
    # but service should check too.
    success = service.verify_code(account_id, email, code_raw)
    
    assert success is False


def test_verify_code_max_attempts(service, mock_verification_repo):
    """Test verification fails after max attempts."""
    account_id = "user-1"
    email = "test@example.com"
    code_raw = "123456"
    code_hash = service._hash_code(code_raw)
    email_hash = service._hash_email(email)
    
    v_code = EmailVerificationCode(
        account_id=account_id,
        email_hash=email_hash,
        code_hash=code_hash,
        attempts=5,
        max_attempts=5,
        expires_at=utc_now() + timedelta(minutes=15)
    )
    mock_verification_repo.get_active_by_email_hash.return_value = [v_code]
    
    success = service.verify_code(account_id, email, code_raw)
    
    assert success is False
