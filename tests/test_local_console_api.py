"""Tests for the local-only console API."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock
from pydantic import SecretStr

from intake.local_console.app import app
from intake.config import get_settings, reset_settings
from intake.local_console.review_service import LocalQuoteReviewService, LocalDecryptedQuoteReview
from intake.sync.models import HostedQuoteProjection

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def mock_review_service():
    from intake.local_console.api import get_local_review_service
    service = MagicMock(spec=LocalQuoteReviewService)
    app.dependency_overrides[get_local_review_service] = lambda: service
    yield service
    app.dependency_overrides = {}

def test_local_status_redaction(client):
    """Verify that local status endpoint redacts sensitive values."""
    settings = get_settings()
    settings.intake_local_sync_token = SecretStr("secret-token")
    settings.intake_dev_encryption_key = SecretStr("secret-key")
    
    response = client.get("/api/local/status")
    assert response.status_code == 200
    data = response.json()
    
    assert data["sync_auth_configured"] is True
    assert data["encryption_key_configured"] is True
    
    # Ensure raw values are NOT present
    assert "secret-token" not in str(data)
    assert "secret-key" not in str(data)

def test_local_pending_quotes(client, mock_review_service):
    """Verify that pending quotes are returned from the local service."""
    mock_review_service.get_pending_reviews.return_value = [
        HostedQuoteProjection(
            quote_id="q1",
            status="submitted",
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00",
            has_encrypted_payload=True,
            upload_count=0
        )
    ]
    
    response = client.get("/api/local/quotes/pending")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["quote_id"] == "q1"

def test_local_quote_review_decrypted(client, mock_review_service):
    """Verify that the review endpoint returns decrypted data."""
    from datetime import datetime
    mock_review_service.get_decrypted_review.return_value = LocalDecryptedQuoteReview(
        quote_id="q1",
        status="reviewing",
        created_at=datetime.now(),
        exact_location="123 Decrypted St",
        access_notes="Door code 1234"
    )
    
    response = client.get("/api/local/quotes/q1/review")
    assert response.status_code == 200
    data = response.json()
    
    assert data["exact_location"] == "123 Decrypted St"
    assert data["access_notes"] == "Door code 1234"
