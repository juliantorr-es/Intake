"""Tests for quote intake API flow."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from intake.app import app
from intake.api.deps import get_current_account_id
from intake.domain.quotes import Quote, QuoteStatus, QuoteServiceLane
from intake.services.quote_service import get_quote_service

@pytest.fixture
def client():
    # Clear overrides before each test
    app.dependency_overrides = {}
    return TestClient(app)

@pytest.fixture
def mock_quote_service():
    service = MagicMock()
    app.dependency_overrides[get_quote_service] = lambda: service
    return service

def test_location_endpoint_empty_body(client, mock_quote_service):
    """Test that location endpoint accepts an empty JSON body."""
    app.dependency_overrides[get_current_account_id] = lambda: "user-1"
    
    mock_quote = Quote(id="quote-1", account_id="user-1", status=QuoteStatus.DRAFT)
    mock_quote_service.add_location.return_value = mock_quote
    
    # Send minimal valid body according to QuoteLocationRequest
    response = client.post("/api/quotes/quote-1/location", json={"general_service_area": "Test Area"})
    assert response.status_code == 200
    
    # Send empty body should still succeed as fields are optional
    response = client.post("/api/quotes/quote-1/location", json={})
    assert response.status_code == 200
    
    # Verify service was called with defaults
    mock_quote_service.add_location.assert_called_with(
        quote_id="quote-1",
        general_service_area="Unknown",
        exact_location=""
    )

def test_location_endpoint_dev_encryption(client, mock_quote_service):
    """Test that location endpoint accepts dev_encrypted_exact_location."""
    app.dependency_overrides[get_current_account_id] = lambda: "user-1"
    
    mock_quote = Quote(id="quote-1", account_id="user-1", status=QuoteStatus.DRAFT)
    mock_quote_service.add_location.return_value = mock_quote
    
    payload = {
        "general_service_area": "Test Area",
        "dev_encrypted_exact_location": {"raw": "123 Secret St"}
    }
    response = client.post("/api/quotes/quote-1/location", json=payload)
    assert response.status_code == 200
    
    # Verify service was called with the raw address for encryption
    mock_quote_service.add_location.assert_called_once_with(
        quote_id="quote-1",
        general_service_area="Test Area",
        exact_location="123 Secret St"
    )

def test_location_security_privacy(client, mock_quote_service):
    """Test that exact location is NOT returned in public responses."""
    app.dependency_overrides[get_current_account_id] = lambda: "user-1"
    
    from intake.domain.crypto import EncryptedPayload
    mock_quote = Quote(
        id="quote-1", 
        account_id="user-1", 
        status=QuoteStatus.DRAFT,
        general_service_area="Public Area",
        encrypted_exact_location=EncryptedPayload(ciphertext="enc:Secret", nonce="nonce")
    )
    # Mock get_safe_summary which is used by get_quote_status
    mock_quote_service.get_safe_summary.return_value = mock_quote.get_safe_summary()
    
    response = client.get("/api/quotes/quote-1/status")
    assert response.status_code == 200
    data = response.json()
    
    assert data["general_service_area"] == "Public Area"
    assert "encrypted_exact_location" not in data
    assert "Secret" not in str(data)

def test_submit_endpoint_empty_body(client, mock_quote_service):
    """Test that submit endpoint accepts an empty JSON object."""
    app.dependency_overrides[get_current_account_id] = lambda: "user-1"
    
    mock_quote = Quote(id="quote-1", account_id="user-1", status=QuoteStatus.SUBMITTED)
    mock_quote_service.submit_quote.return_value = mock_quote
    
    response = client.post("/api/quotes/quote-1/submit", json={})
    assert response.status_code == 200
    assert response.json()["success"] is True

def test_quote_flow_authentication_requirement(client):
    """Test that quote flow endpoints require authenticated ownership."""
    # No authentication provided
    response = client.post("/api/quotes/quote-1/location", json={})
    assert response.status_code == 401 # Unauthorized
    
    response = client.post("/api/quotes/quote-1/submit", json={})
    assert response.status_code == 401
