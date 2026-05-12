"""Tests for passkey domain shapes and challenge model."""

import base64
import uuid
from datetime import datetime, timedelta

import pytest

from intake.domain.passkeys import (
    PasskeyChallenge,
    PasskeyChallengeStatus,
    PasskeyCredential,
    PasskeyRegistrationOptions,
    PasskeyType,
)


def test_passkey_challenge_creation():
    """Test creating a passkey challenge."""
    challenge = PasskeyChallenge.create_registration_challenge(
        rp_id="localhost",
        origin="http://localhost:8000",
    )

    assert challenge.rp_id == "localhost"
    assert challenge.origin == "http://localhost:8000"
    assert challenge.status == PasskeyChallengeStatus.PENDING
    assert challenge.account_id is None
    assert challenge.consumed_at is None
    assert challenge.id is not None
    assert challenge.challenge is not None
    assert challenge.created_at is not None
    assert challenge.expires_at > challenge.created_at


def test_passkey_challenge_with_account():
    """Test creating a challenge with an account."""
    challenge = PasskeyChallenge.create_registration_challenge(
        rp_id="localhost",
        origin="http://localhost:8000",
        account_id="account-123",
        expiry_seconds=600,
    )

    assert challenge.account_id == "account-123"


def test_passkey_challenge_authentication():
    """Test creating an authentication challenge."""
    challenge = PasskeyChallenge.create_authentication_challenge(
        rp_id="localhost",
        origin="http://localhost:8000",
    )

    assert challenge.rp_id == "localhost"
    assert challenge.origin == "http://localhost:8000"
    assert challenge.status == PasskeyChallengeStatus.PENDING


def test_passkey_challenge_is_valid():
    """Test challenge validity checking."""
    # Create a challenge that expires in 5 minutes
    challenge = PasskeyChallenge(
        id=uuid.uuid4().hex,
        challenge=base64.b64encode(uuid.uuid4().bytes).decode(),
        rp_id="localhost",
        origin="http://localhost:8000",
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(minutes=5),
    )

    assert challenge.is_valid is True


def test_passkey_challenge_is_not_valid_consumed():
    """Test that consumed challenge is not valid."""
    challenge = PasskeyChallenge(
        id=uuid.uuid4().hex,
        challenge=base64.b64encode(uuid.uuid4().bytes).decode(),
        rp_id="localhost",
        origin="http://localhost:8000",
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(minutes=5),
        status=PasskeyChallengeStatus.CONSUMED,
    )

    assert challenge.is_valid is False


def test_passkey_challenge_is_not_valid_expired():
    """Test that expired challenge is not valid."""
    challenge = PasskeyChallenge(
        id=uuid.uuid4().hex,
        challenge=base64.b64encode(uuid.uuid4().bytes).decode(),
        rp_id="localhost",
        origin="http://localhost:8000",
        created_at=datetime.utcnow() - timedelta(minutes=10),
        expires_at=datetime.utcnow() - timedelta(minutes=5),
    )

    assert challenge.is_valid is False


def test_passkey_challenge_mark_consumed():
    """Test marking a challenge as consumed."""
    challenge = PasskeyChallenge.create_registration_challenge(
        rp_id="localhost",
        origin="http://localhost:8000",
    )

    assert challenge.status == PasskeyChallengeStatus.PENDING
    assert challenge.consumed_at is None

    challenge.mark_consumed()

    assert challenge.status == PasskeyChallengeStatus.CONSUMED
    assert challenge.consumed_at is not None


def test_passkey_challenge_aggregate_type():
    """Test challenge aggregate type."""
    from intake.domain.events import EventAggregateType

    challenge = PasskeyChallenge.create_registration_challenge(
        rp_id="localhost",
        origin="http://localhost:8000",
    )

    assert challenge.aggregate_type == EventAggregateType.PASSKEY


def test_passkey_credential_creation():
    """Test creating a passkey credential."""
    credential = PasskeyCredential(
        credential_id=base64.b64encode(b"credential-id").decode(),
        public_key=base64.b64encode(b"public-key-data").decode(),
        counter=0,
        account_id="account-123",
    )

    assert credential.credential_id == base64.b64encode(b"credential-id").decode()
    assert credential.public_key == base64.b64encode(b"public-key-data").decode()
    assert credential.counter == 0
    assert credential.account_id == "account-123"
    assert credential.credential_type == PasskeyType.PUBLIC_KEY
    assert credential.registered_at is not None


def test_passkey_credential_defaults():
    """Test passkey credential defaults."""
    credential = PasskeyCredential(
        credential_id=base64.b64encode(b"cred-id").decode(),
        public_key=base64.b64encode(b"pub-key").decode(),
        account_id="account-1",
    )

    assert credential.id is not None
    assert credential.last_used_at is None
    assert credential.name is None


def test_passkey_registration_options():
    """Test passkey registration options."""
    options = PasskeyRegistrationOptions(
        challenge="challenge-b64",
        rp={"id": "localhost", "name": "Test RP"},
        user={"id": "user-id", "name": "user-name", "displayName": "User Display"},
        pubKeyCredParams=[{"type": "public-key", "alg": -7}],
    )

    assert options.challenge == "challenge-b64"
    assert options.rp == {"id": "localhost", "name": "Test RP"}
    assert options.user == {"id": "user-id", "name": "user-name", "displayName": "User Display"}
    assert options.pubKeyCredParams == [{"type": "public-key", "alg": -7}]


def test_passkey_challenge_status_values():
    """Test passkey challenge status values."""
    assert PasskeyChallengeStatus.PENDING.value == "pending"
    assert PasskeyChallengeStatus.CONSUMED.value == "consumed"
    assert PasskeyChallengeStatus.EXPIRED.value == "expired"


def test_passkey_type_values():
    """Test passkey type values."""
    assert PasskeyType.PUBLIC_KEY.value == "public_key"


def test_passkey_challenge_model_serialization():
    """Test that passkey challenge can be serialized."""
    challenge = PasskeyChallenge.create_registration_challenge(
        rp_id="localhost",
        origin="http://localhost:8000",
    )

    # Should be able to serialize to dict
    data = challenge.model_dump()
    assert "id" in data
    assert "challenge" in data
    assert "rp_id" in data
    assert "origin" in data
    assert "status" in data


def test_passkey_credential_model_serialization():
    """Test that passkey credential can be serialized."""
    credential = PasskeyCredential(
        credential_id=base64.b64encode(b"cred-id").decode(),
        public_key=base64.b64encode(b"pub-key").decode(),
        account_id="account-1",
    )

    data = credential.model_dump()
    assert "id" in data
    assert "credential_id" in data
    assert "public_key" in data
    assert "account_id" in data
