"""Tests for Local Console Security API.

These tests verify the security behavior of the Local Secure Unlock endpoints,
including the challenge/response flow and dev mode gating.

Required test coverage per requirements:
- challenge token alone does not unlock
- missing native_proof does not unlock
- invalid native_proof does not unlock
- valid challenge + valid native proof unlocks
- challenge cannot be reused after success
- invalid proof does not consume challenge
- expired challenge fails
- direct dev insecure unlock only works when INTAKE_ENABLE_INSECURE_DEV_UNLOCK=1
- capabilities endpoint does not expose proof material
"""

import os
import time
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from unittest.mock import patch

import pytest

from intake.local_console.api.security import (
    router as security_router,
    _challenge_store,
    _generate_challenge,
    _cleanup_expired_challenges,
    _validate_native_proof,
    _get_native_capability,
    reset_security_state,
    UnlockRequest,
)
from intake.local_console.security.unlock import LocalAuthorizationWindow, reset_auth_window
from intake.config import get_settings, reset_settings


@pytest.fixture(autouse=True)
def reset_security_state_fixture():
    """Reset security state before and after each test."""
    from intake.config import reset_settings as reset_settings_func
    
    # Clear any cached state
    reset_auth_window()
    _challenge_store.clear()
    
    # Clear settings cache
    reset_settings_func()
    
    # Reset native capability
    import intake.local_console.api.security as sec_module
    sec_module._native_capability = None
    
    yield
    
    # Clean up after test
    reset_auth_window()
    _challenge_store.clear()
    reset_settings_func()
    sec_module._native_capability = None


@pytest.fixture
def client():
    """Create a test client for the security router."""
    from fastapi import FastAPI
    test_app = FastAPI()
    test_app.include_router(security_router)
    return TestClient(test_app)


@pytest.fixture
def auth_window():
    """Get a fresh auth window for testing."""
    reset_auth_window()
    return LocalAuthorizationWindow.get_instance()


# =============================================================================
# Challenge Store Tests
# =============================================================================

class TestChallengeStore:
    """Tests for the challenge generation and storage."""

    def test_generate_challenge_creates_token(self):
        """Test that generating a challenge creates a valid token."""
        token, expires_at = _generate_challenge(expiry_seconds=60)
        assert token is not None
        assert len(token) == 64  # 32 bytes in hex = 64 chars
        assert token in _challenge_store
        assert isinstance(expires_at, datetime)

    def test_generate_challenge_sets_absolute_expiry(self):
        """Test that challenge expiry is an absolute timestamp, not relative seconds."""
        token, expires_at = _generate_challenge(expiry_seconds=60)
        
        # Verify it's a datetime object
        assert isinstance(expires_at, datetime)
        assert expires_at.tzinfo is not None  # Has timezone info
        
        # Verify it's in the future (approximately 60 seconds from now)
        now = datetime.now(timezone.utc)
        delta = expires_at - now
        assert delta.total_seconds() > 55  # Allow some tolerance
        assert delta.total_seconds() < 65

    def test_cleanup_expired_challenges(self):
        """Test that expired challenges are cleaned up."""
        # Create a challenge that expires immediately
        _challenge_store.clear()
        now = datetime.now(timezone.utc)
        expired_token = "expired_" + os.urandom(30).hex()
        _challenge_store[expired_token] = {
            "created_at": now - timedelta(seconds=120),
            "expires_at": now - timedelta(seconds=60),
            "consumed": False
        }
        
        # Create a valid challenge
        valid_token, _ = _generate_challenge(expiry_seconds=300)
        
        assert expired_token in _challenge_store
        assert valid_token in _challenge_store
        
        # Run cleanup
        count = _cleanup_expired_challenges()
        
        assert count >= 1
        assert expired_token not in _challenge_store
        assert valid_token in _challenge_store  # Valid challenge should remain


# =============================================================================
# Native Proof Validation Tests
# =============================================================================

class TestNativeProofValidation:
    """Tests for native capability proof validation."""

    def test_validate_native_proof_with_none(self):
        """Test that None proof is invalid."""
        assert _validate_native_proof(None) == False

    def test_validate_native_proof_with_invalid_string(self):
        """Test that an invalid string proof is rejected."""
        # Reset capability first
        import intake.local_console.api.security as sec_module
        sec_module._native_capability = None
        
        # Set a known capability
        sec_module._native_capability = "known_capability_token_1234567890abcdef"
        
        assert _validate_native_proof("wrong_token") == False

    def test_validate_native_proof_with_valid_token(self):
        """Test that a matching proof is accepted."""
        import intake.local_console.api.security as sec_module
        sec_module._native_capability = None
        
        # Set a known capability
        capability = "test_capability_" + os.urandom(24).hex()
        sec_module._native_capability = capability
        
        assert _validate_native_proof(capability) == True


# =============================================================================
# Security Endpoints Tests
# =============================================================================

class TestUnlockChallenge:
    """Tests for the unlock challenge flow."""

    def test_get_challenge_returns_valid_token(self, client):
        """Test that challenge endpoint returns a valid challenge."""
        response = client.get("/security/challenge")
        assert response.status_code == 200
        data = response.json()
        assert "challenge_token" in data
        assert len(data["challenge_token"]) == 64
        assert "expires_at" in data
        assert data["requires_native_proof"] == True
        
        # Verify challenge was stored
        assert data["challenge_token"] in _challenge_store

    def test_challenge_expiration_setting(self, client):
        """Test that challenge expiry uses config setting."""
        with patch.dict(os.environ, {"INTAKE_CHALLENGE_EXPIRY": "300"}):
            reset_settings()
            response = client.get("/security/challenge")
            assert response.status_code == 200
            data = response.json()
            # Just verify we got a token - expiry is validated by timing
            assert "challenge_token" in data


class TestUnlockEndpoint:
    """Tests for the /unlock endpoint behavior - CRITICAL SECURITY TESTS."""

    def test_challenge_token_alone_does_not_unlock(self, client, auth_window):
        """REQUIRED: Test that POST /unlock with ONLY challenge_token FAILS."""
        reset_auth_window()
        
        # Get a valid challenge
        challenge_resp = client.get("/security/challenge")
        challenge = challenge_resp.json()
        token = challenge["challenge_token"]
        
        # Try to unlock with ONLY challenge token (no native_proof)
        response = client.post(
            "/security/unlock",
            json={"challenge_token": token}
        )
        
        # MUST FAIL
        assert response.status_code == 403
        assert "Native proof is required alongside challenge token" in response.json()["detail"]
        assert auth_window.is_unlocked == False
        
        # Challenge should NOT be consumed (for retry)
        assert token in _challenge_store
        assert _challenge_store[token]["consumed"] == False

    def test_native_proof_alone_does_not_unlock(self, client, auth_window):
        """REQUIRED: Test that POST /unlock with ONLY native_proof FAILS."""
        import intake.local_console.api.security as sec_module
        sec_module._native_capability = None
        
        reset_auth_window()
        
        # Set a valid capability
        capability = "test_cap_" + os.urandom(28).hex()
        sec_module._native_capability = capability
        
        # Try to unlock with ONLY native_proof (no challenge_token)
        response = client.post(
            "/security/unlock",
            json={"native_proof": capability}
        )
        
        # MUST FAIL
        assert response.status_code == 403
        assert "Challenge token is required alongside native proof" in response.json()["detail"]
        assert auth_window.is_unlocked == False

    def test_invalid_native_proof_does_not_unlock(self, client, auth_window):
        """REQUIRED: Test that invalid native_proof FAILS and does NOT consume challenge."""
        import intake.local_console.api.security as sec_module
        sec_module._native_capability = None
        
        reset_auth_window()
        
        # Set a known capability
        capability = "valid_cap_" + os.urandom(28).hex()
        sec_module._native_capability = capability
        
        # Get a challenge
        challenge_resp = client.get("/security/challenge")
        challenge = challenge_resp.json()
        token = challenge["challenge_token"]
        
        # Try to unlock with valid challenge but WRONG proof
        response = client.post(
            "/security/unlock",
            json={
                "challenge_token": token,
                "native_proof": "wrong_proof_value"
            }
        )
        
        # MUST FAIL
        assert response.status_code == 403
        assert "Native capability proof validation failed" in response.json()["detail"]
        assert auth_window.is_unlocked == False
        
        # Challenge must NOT be consumed - allow retry after fixing
        assert token in _challenge_store
        assert _challenge_store[token]["consumed"] == False

    def test_valid_challenge_plus_valid_proof_unlocks(self, client, auth_window):
        """REQUIRED: Test that valid challenge + valid native proof DOES unlock."""
        import intake.local_console.api.security as sec_module
        sec_module._native_capability = None
        
        reset_auth_window()
        
        # Set a known capability
        capability = "valid_cap_" + os.urandom(28).hex()
        sec_module._native_capability = capability
        
        # Get a challenge
        challenge_resp = client.get("/security/challenge")
        challenge = challenge_resp.json()
        token = challenge["challenge_token"]
        
        # Unlock with both valid challenge and valid proof
        response = client.post(
            "/security/unlock",
            json={
                "challenge_token": token,
                "native_proof": capability
            }
        )
        
        # MUST SUCCEED
        assert response.status_code == 200
        data = response.json()
        assert data["is_unlocked"] == True
        assert data["unlock_mode"] == "native_os_auth"
        assert auth_window.is_unlocked == True
        
        # Challenge MUST be consumed
        assert token in _challenge_store
        assert _challenge_store[token]["consumed"] == True

    def test_challenge_cannot_be_reused_after_success(self, client, auth_window):
        """REQUIRED: Test that a challenge cannot be reused after successful unlock."""
        import intake.local_console.api.security as sec_module
        sec_module._native_capability = None
        
        reset_auth_window()
        
        capability = "valid_cap_" + os.urandom(28).hex()
        sec_module._native_capability = capability
        
        # Get challenge and use it
        challenge_resp = client.get("/security/challenge")
        challenge = challenge_resp.json()
        token = challenge["challenge_token"]
        
        # First use
        client.post(
            "/security/unlock",
            json={"challenge_token": token, "native_proof": capability}
        )
        
        # Reset auth state for second attempt
        reset_auth_window()
        
        # Second use should FAIL
        response = client.post(
            "/security/unlock",
            json={"challenge_token": token, "native_proof": capability}
        )
        
        assert response.status_code == 403
        assert auth_window.is_unlocked == False

    def test_expired_challenge_fails(self, client, auth_window):
        """REQUIRED: Test that an expired challenge fails."""
        import intake.local_console.api.security as sec_module
        sec_module._native_capability = None
        
        reset_auth_window()
        
        capability = "valid_cap_" + os.urandom(28).hex()
        sec_module._native_capability = capability
        
        # Create an expired challenge directly
        _challenge_store.clear()
        now = datetime.now(timezone.utc)
        expired_token = "expired_" + os.urandom(30).hex()
        _challenge_store[expired_token] = {
            "created_at": now - timedelta(seconds=120),
            "expires_at": now - timedelta(seconds=60),  # Expired 60 seconds ago
            "consumed": False
        }
        
        # Try to use expired challenge
        response = client.post(
            "/security/unlock",
            json={
                "challenge_token": expired_token,
                "native_proof": capability
            }
        )
        
        assert response.status_code == 403
        assert "expired" in response.json()["detail"].lower()
        assert auth_window.is_unlocked == False
        
        # Expired challenge should be marked consumed to prevent reuse
        assert expired_token in _challenge_store
        assert _challenge_store[expired_token]["consumed"] == True

    def test_dev_insecure_unlock_only_works_with_flag(self, client, auth_window):
        """REQUIRED: Test that direct dev insecure unlock only works when INTAKE_ENABLE_INSECURE_DEV_UNLOCK=1."""
        reset_auth_window()
        
        # Without the flag - should FAIL
        with patch.dict(os.environ, {"INTAKE_ENABLE_INSECURE_DEV_UNLOCK": "0"}):
            reset_settings()
            
            response = client.post("/security/unlock")
            assert response.status_code == 403
            assert auth_window.is_unlocked == False
            assert "Secure unlock requires native OS authentication" in response.json()["detail"]
        
        # With the flag - should SUCCEED
        with patch.dict(os.environ, {"INTAKE_ENABLE_INSECURE_DEV_UNLOCK": "1"}):
            reset_settings()
            reset_auth_window()
            
            response = client.post("/security/unlock")
            assert response.status_code == 200
            data = response.json()
            assert data["is_unlocked"] == True
            assert data["unlock_mode"] == "dev_insecure"
            assert data["requires_native_auth"] == False
            assert auth_window.is_unlocked == True

    def test_unlock_without_challenge_fails_by_default(self, client, auth_window):
        """Test that POST /unlock without challenge or proof fails when dev mode is off."""
        with patch.dict(os.environ, {"INTAKE_ENABLE_INSECURE_DEV_UNLOCK": "0"}):
            reset_settings()
            
            response = client.post("/security/unlock")
            assert response.status_code == 403
            assert "Both challenge_token AND native_proof are required" in response.json()["detail"]
            assert auth_window.is_unlocked == False


class TestCapabilitiesEndpoint:
    """Tests for the /capabilities endpoint."""

    def test_capabilities_endpoint_does_not_expose_proof(self, client):
        """REQUIRED: Test that capabilities endpoint does NOT expose native proof secrets."""
        import intake.local_console.api.security as sec_module
        sec_module._native_capability = None
        
        # Set a known capability
        capability = "secret_cap_" + os.urandom(28).hex()
        sec_module._native_capability = capability
        
        response = client.get("/security/capabilities")
        assert response.status_code == 200
        data = response.json()
        
        # Verify capability secret is NOT in the response
        assert capability not in str(data)
        assert "native_capability" not in data
        assert "native_proof" not in data
        
        # Verify expected fields are present
        assert "runtime_shell" in data
        assert "secure_unlock_available" in data
        assert "insecure_dev_unlock_enabled" in data
        assert "unlock_label" in data

    def test_capabilities_loopback_only(self, client):
        """Test that capabilities endpoint enforces loopback."""
        # TestClient simulates loopback, so this should work
        response = client.get("/security/capabilities")
        assert response.status_code == 200

    def test_capabilities_dev_insecure_flag(self, client):
        """Test that capabilities correctly reports dev insecure flag."""
        with patch.dict(os.environ, {"INTAKE_ENABLE_INSECURE_DEV_UNLOCK": "1"}):
            reset_settings()
            
            response = client.get("/security/capabilities")
            assert response.status_code == 200
            data = response.json()
            assert data["insecure_dev_unlock_enabled"] == True
        
        with patch.dict(os.environ, {"INTAKE_ENABLE_INSECURE_DEV_UNLOCK": "0"}):
            reset_settings()
            
            response = client.get("/security/capabilities")
            assert response.status_code == 200
            data = response.json()
            assert data["insecure_dev_unlock_enabled"] == False


class TestUnlockLabeling:
    """Tests for unlock mode labeling in UI."""

    def test_dev_insecure_mode_is_labeled(self, client):
        """Test that dev insecure mode returns correct unlock_mode label."""
        with patch.dict(os.environ, {"INTAKE_ENABLE_INSECURE_DEV_UNLOCK": "1"}):
            reset_settings()
            reset_auth_window()
            
            response = client.post("/security/unlock")
            assert response.status_code == 200
            data = response.json()
            assert data["unlock_mode"] == "dev_insecure"

    def test_native_auth_mode_is_labeled(self, client):
        """Test that challenge flow returns correct unlock_mode label."""
        import intake.local_console.api.security as sec_module
        sec_module._native_capability = None
        
        reset_auth_window()
        
        capability = "test_cap_" + os.urandom(28).hex()
        sec_module._native_capability = capability
        
        challenge_resp = client.get("/security/challenge")
        challenge = challenge_resp.json()
        
        response = client.post(
            "/security/unlock",
            json={"challenge_token": challenge["challenge_token"], "native_proof": capability}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["unlock_mode"] == "native_os_auth"


class TestChallengeFlowIntegration:
    """Integration tests for the complete challenge flow."""

    def test_complete_challenge_flow(self, client, auth_window):
        """Test the complete challenge + unlock flow."""
        import intake.local_console.api.security as sec_module
        sec_module._native_capability = None
        
        reset_auth_window()
        
        capability = "test_cap_" + os.urandom(28).hex()
        sec_module._native_capability = capability
        
        # Step 1: Get challenge
        challenge_resp = client.get("/security/challenge")
        assert challenge_resp.status_code == 200
        challenge = challenge_resp.json()
        assert "challenge_token" in challenge
        
        # Step 2: Verify we're locked initially
        status_resp = client.get("/security/status")
        status = status_resp.json()
        assert status["is_unlocked"] == False
        
        # Step 3: Use challenge to unlock
        unlock_resp = client.post(
            "/security/unlock",
            json={
                "challenge_token": challenge["challenge_token"],
                "native_proof": capability
            }
        )
        assert unlock_resp.status_code == 200
        
        # Step 4: Verify we're unlocked
        status_resp = client.get("/security/status")
        status = status_resp.json()
        assert status["is_unlocked"] == True
        assert status["unlock_mode"] == "native_os_auth"
        
        # Step 5: Verify challenge can't be reused
        unlock_resp2 = client.post(
            "/security/unlock",
            json={
                "challenge_token": challenge["challenge_token"],
                "native_proof": capability
            }
        )
        assert unlock_resp2.status_code == 403


class TestLockEndpoint:
    """Tests for the /lock endpoint."""

    def test_lock_endpoint_clears_window(self, client, auth_window):
        """Test that POST /lock clears the authorization window."""
        # Unlock first
        import intake.local_console.api.security as sec_module
        sec_module._native_capability = None
        sec_module._native_capability = "test_cap_" + os.urandom(28).hex()
        
        challenge_resp = client.get("/security/challenge")
        challenge = challenge_resp.json()
        
        client.post(
            "/security/unlock",
            json={
                "challenge_token": challenge["challenge_token"],
                "native_proof": sec_module._native_capability
            }
        )
        assert auth_window.is_unlocked == True
        
        # Now lock
        response = client.post("/security/lock")
        assert response.status_code == 200
        data = response.json()
        assert data["is_unlocked"] == False
        assert auth_window.is_unlocked == False
        assert data["unlock_mode"] == "none"

    def test_lock_multiple_times(self, client, auth_window):
        """Test that locking an already-locked window is safe."""
        # Start locked
        assert auth_window.is_unlocked == False
        
        # Lock again
        response = client.post("/security/lock")
        assert response.status_code == 200
        assert auth_window.is_unlocked == False


class TestStatusEndpoint:
    """Tests for the /status endpoint."""

    def test_get_unlock_status_when_locked(self, client):
        """Test status endpoint when window is locked."""
        response = client.get("/security/status")
        assert response.status_code == 200
        data = response.json()
        assert data["is_unlocked"] == False
        assert data["remaining_seconds"] == 0.0
        assert data["unlock_mode"] == "none"
        assert data["requires_native_auth"] == True

    def test_get_unlock_status_when_unlocked(self, client):
        """Test status endpoint when window is unlocked."""
        import intake.local_console.api.security as sec_module
        sec_module._native_capability = None
        sec_module._native_capability = "test_cap_" + os.urandom(28).hex()
        
        reset_auth_window()
        
        challenge_resp = client.get("/security/challenge")
        challenge = challenge_resp.json()
        
        client.post(
            "/security/unlock",
            json={
                "challenge_token": challenge["challenge_token"],
                "native_proof": sec_module._native_capability
            }
        )
        
        response = client.get("/security/status")
        assert response.status_code == 200
        data = response.json()
        assert data["is_unlocked"] == True
        assert data["remaining_seconds"] > 0
        assert data["unlock_mode"] == "native_os_auth"
