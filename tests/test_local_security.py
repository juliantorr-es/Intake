"""Tests for Local Secure Unlock and protected actions."""

import pytest
import time
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from intake.config import get_settings, reset_settings
from intake.local_console.security.unlock import get_auth_window, reset_auth_window
from intake.local_console.app import app

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture(autouse=True)
def setup_settings():
    reset_settings()
    # Ensure unlock is required for tests
    settings = get_settings()
    settings.intake_require_local_unlock_for_decrypt = True
    settings.intake_local_unlock_ttl_seconds = 2 # Short TTL for testing
    yield
    reset_settings()

@pytest.fixture(autouse=True)
def clean_auth_window():
    window = get_auth_window()
    window.lock()
    yield
    window.lock()

def test_security_status_starts_locked(client):
    """Security status should start as locked."""
    response = client.get("/api/local/security/status")
    assert response.status_code == 200
    data = response.json()
    assert data["is_unlocked"] is False
    assert data["seconds_remaining"] == 0.0

def test_unlock_creates_authorization_window(client):
    """Unlock endpoint should create an authorization window."""
    response = client.post("/api/local/security/unlock")
    assert response.status_code == 200
    data = response.json()
    assert data["is_unlocked"] is True
    assert data["seconds_remaining"] > 0.0
    
    # Check status endpoint
    response = client.get("/api/local/security/status")
    assert response.json()["is_unlocked"] is True

def test_lock_clears_authorization_window(client):
    """Lock endpoint should clear the authorization window."""
    client.post("/api/local/security/unlock")
    assert get_auth_window().is_unlocked is True
    
    response = client.post("/api/local/security/lock")
    assert response.status_code == 200
    assert response.json()["is_unlocked"] is False
    assert get_auth_window().is_unlocked is False

def test_unlock_expires_after_ttl(client):
    """Unlock window should expire after the configured TTL."""
    settings = get_settings()
    settings.intake_local_unlock_ttl_seconds = 1
    
    client.post("/api/local/security/unlock")
    assert get_auth_window().is_unlocked is True
    
    time.sleep(1.1)
    assert get_auth_window().is_unlocked is False
    
    response = client.get("/api/local/security/status")
    assert response.json()["is_unlocked"] is False

def test_quote_review_locked_redacts_sensitive_fields(client, monkeypatch):
    """Quote review should redact sensitive fields when locked."""
    from intake.local_console.api.main import get_local_review_service
    from intake.local_console.review_service import LocalDecryptedQuoteReview, UploadEvidence
    
    class MockService:
        def get_decrypted_review(self, quote_id):
            return LocalDecryptedQuoteReview(
                quote_id=quote_id,
                status="submitted",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                is_locked=True,
                exact_location=None,
                access_notes=None,
                questionnaire_answers=None,
                upload_evidence=[UploadEvidence(
                    file_id="f1",
                    original_filename="[LOCKED]",
                    content_type="image/jpeg",
                    size_bytes=100,
                    sha256="abc",
                    storage_provider="local",
                    stored_at=datetime.now(timezone.utc)
                )]
            )
    
    app.dependency_overrides[get_local_review_service] = lambda: MockService()
    
    # Ensure locked
    get_auth_window().lock()
    
    response = client.get("/api/local/quotes/q1/review")
    app.dependency_overrides.clear()
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["is_locked"] is True
    assert data["exact_location"] is None
    assert data["access_notes"] is None
    assert data["questionnaire_answers"] is None
    assert data["upload_evidence"][0]["original_filename"] == "[LOCKED]"

def test_quote_review_unlocked_includes_sensitive_fields(client, monkeypatch):
    """Quote review should include sensitive fields when unlocked."""
    from intake.local_console.api.main import get_local_review_service
    from intake.local_console.review_service import LocalDecryptedQuoteReview, UploadEvidence
    
    class MockService:
        def get_decrypted_review(self, quote_id):
            return LocalDecryptedQuoteReview(
                quote_id=quote_id,
                status="submitted",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                is_locked=False,
                exact_location="123 Main St",
                access_notes="Gate code 1234",
                questionnaire_answers={"q1": "a1"},
                upload_evidence=[UploadEvidence(
                    file_id="f1",
                    original_filename="secret_file.pdf",
                    content_type="image/jpeg",
                    size_bytes=100,
                    sha256="abc",
                    storage_provider="local",
                    stored_at=datetime.now(timezone.utc)
                )]
            )
    
    app.dependency_overrides[get_local_review_service] = lambda: MockService()
    
    # Unlock
    client.post("/api/local/security/unlock")
    
    response = client.get("/api/local/quotes/q1/review")
    app.dependency_overrides.clear()
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["is_locked"] is False
    assert data["exact_location"] == "123 Main St"
    assert data["access_notes"] == "Gate code 1234"
    assert data["questionnaire_answers"] == {"q1": "a1"}
    assert data["upload_evidence"][0]["original_filename"] == "secret_file.pdf"
