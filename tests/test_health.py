"""Tests for health endpoint."""

import pytest
from fastapi.testclient import TestClient

from intake.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoint(client):
    """Test that health endpoint returns ok status."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_ready_endpoint(client):
    """Test that ready endpoint returns ready status."""
    response = client.get("/api/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["ready"] is True
    assert data["database"] is True
