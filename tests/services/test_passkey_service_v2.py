import pytest
from unittest.mock import MagicMock, patch
from intake.services.passkey_service import PasskeyService
from intake.domain.passkeys import ChallengeAction, PasskeyChallengeStatus
from webauthn.registration.verify_registration_response import VerifiedRegistration
from webauthn.authentication.verify_authentication_response import VerifiedAuthentication
import json
import base64
from webauthn.helpers import bytes_to_base64url

@pytest.fixture
def passkey_service():
    return PasskeyService(
        account_repo=MagicMock(),
        passkey_repo=MagicMock(),
        challenge_repo=MagicMock(),
        event_repo=MagicMock(),
    )

@pytest.mark.asyncio
async def test_verify_registration_v2_fields(passkey_service):
    # Mock data
    challenge_value = "test-challenge"
    credential_data = {
        "id": "cred-id",
        "response": {
            "clientDataJSON": base64.urlsafe_b64encode(json.dumps({
                "challenge": challenge_value,
                "origin": "http://localhost:8003"
            }).encode()).decode(),
            "attestationObject": "mock-attestation"
        },
        "authenticatorAttachment": "platform"
    }
    
    # Mock challenge model
    challenge_model = MagicMock()
    challenge_model.id = "challenge-id"
    challenge_model.status = PasskeyChallengeStatus.PENDING
    challenge_model.expires_at = MagicMock() # Will be handled by utc_is_expired mock
    challenge_model.action = ChallengeAction.REGISTER
    challenge_model.account_id = None
    
    passkey_service._challenge_repo.get_by_challenge_value.return_value = challenge_model
    
    # Mock VerifiedRegistration (WebAuthn v2)
    mock_verification = MagicMock(spec=VerifiedRegistration)
    mock_verification.credential_id = b"cred-id-bytes"
    mock_verification.credential_public_key = b"pub-key-bytes"
    mock_verification.sign_count = 5
    mock_verification.credential_device_type = "single_device"
    mock_verification.credential_backed_up = True
    
    with patch("intake.services.passkey_service.verify_registration_response", return_value=mock_verification), \
         patch("intake.domain.time.utc_is_expired", return_value=False), \
         patch("intake.services.passkey_service.base64url_to_bytes", return_value=b"challenge-bytes"):
        
        credential, account = passkey_service.verify_registration(credential_data)
        
        # Verify field access
        assert credential.credential_id == bytes_to_base64url(b"cred-id-bytes")
        assert credential.public_key == bytes_to_base64url(b"pub-key-bytes")
        assert credential.sign_count == 5
        assert credential.backup_eligible is False # single_device
        assert credential.backup_state is True
        assert credential.device_label == "platform"

@pytest.mark.asyncio
async def test_verify_authentication_v2_fields(passkey_service):
    # Mock data
    challenge_value = "test-challenge"
    credential_data = {
        "id": "cred-id",
        "response": {
            "clientDataJSON": base64.urlsafe_b64encode(json.dumps({
                "challenge": challenge_value,
                "origin": "http://localhost:8003"
            }).encode()).decode(),
            "authenticatorData": "mock-auth-data",
            "signature": "mock-signature"
        }
    }
    
    # Mock challenge model
    challenge_model = MagicMock()
    challenge_model.id = "challenge-id"
    challenge_model.status = PasskeyChallengeStatus.PENDING
    challenge_model.expires_at = MagicMock()
    challenge_model.action = ChallengeAction.LOGIN
    
    passkey_service._challenge_repo.get_by_challenge_value.return_value = challenge_model
    
    # Mock credential model
    credential_model = MagicMock()
    credential_model.id = "db-cred-id"
    credential_model.credential_id = "cred-id"
    credential_model.public_key = "pub-key-b64"
    credential_model.sign_count = 10
    credential_model.account_id = "account-id"
    
    passkey_service._passkey_repo.get_credential.return_value = credential_model
    account_mock = MagicMock()
    account_mock.id = "account-id"
    passkey_service._account_repo.get_by_id.return_value = account_mock
    
    # Mock VerifiedAuthentication (WebAuthn v2)
    mock_verification = MagicMock(spec=VerifiedAuthentication)
    mock_verification.credential_id = b"cred-id-bytes"
    mock_verification.new_sign_count = 11
    mock_verification.credential_device_type = "multi_device"
    mock_verification.credential_backed_up = True
    
    with patch("intake.services.passkey_service.verify_authentication_response", return_value=mock_verification), \
         patch("intake.domain.time.utc_is_expired", return_value=False), \
         patch("intake.services.passkey_service.base64url_to_bytes", return_value=b"bytes"), \
         patch("intake.services.passkey_service.get_session_service", return_value=MagicMock()):
        
        account, session_token = passkey_service.verify_authentication(credential_data)
        
        # Verify update call
        passkey_service._passkey_repo.update_after_login.assert_called_once_with(
            credential_id="cred-id",
            new_sign_count=11,
            backup_eligible=True,
            backup_state=True
        )
