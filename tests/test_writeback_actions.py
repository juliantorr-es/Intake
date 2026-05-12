"""Tests for the QUOTE_REVIEW_START writeback action."""

import pytest
import base64
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from pydantic import SecretStr

from intake.app import app
from intake.config import get_settings, reset_settings
from intake.sync.models import LocalDeviceActionEnvelope
from intake.services.signing_service import LocalDeviceSigningService
from intake.storage.repositories import SyncRepository, QuoteRepository, EventRepository
from intake.domain.quotes import Quote, QuoteStatus
from intake.domain.events import EventAggregateType, EventType

@pytest.fixture
def client():
    app.dependency_overrides = {}
    return TestClient(app)

@pytest.fixture
def sync_token():
    return "test-sync-token"

@pytest.fixture
def setup_auth(sync_token):
    settings = get_settings()
    settings.intake_local_sync_token = SecretStr(sync_token)
    settings.intake_enable_dev_sync_auth = True
    
    # Ensure tables exist
    from intake.storage.db import create_all_tables
    create_all_tables()
    
    yield
    reset_settings()

@pytest.fixture
def signing_service():
    # Use a fixed key for tests to avoid mismatch between fixture calls
    # or ensure they are linked.
    # For now, a fixed key is easiest for testing replay/transitions.
    fixed_private_key = base64.b64encode(b"a" * 32).decode("utf-8")
    return LocalDeviceSigningService(fixed_private_key)

@pytest.fixture
def registered_device(signing_service):
    repo = SyncRepository()
    from intake.sync.models import LocalDevice
    
    device_id = "test-device-1"
    existing = repo.get_device(device_id)
    if existing:
        # Ensure the public key matches our signing service
        # Note: In a real test we might want to update the public key in DB 
        # but here we'll just return the domain object with the CORRECT key 
        # so the verification service (which pulls from DB) will fail if DB is wrong.
        # So let's update the DB if it's different.
        if existing.public_signing_key != signing_service.get_public_key_base64():
            from intake.storage.db import get_session
            with get_session() as session:
                from intake.storage.models import RegisteredDeviceModel
                db_device = session.get(RegisteredDeviceModel, device_id)
                db_device.public_signing_key = signing_service.get_public_key_base64()
                session.add(db_device)
                session.commit()
            return repo.get_device(device_id).to_domain()
        return existing.to_domain()
        
    device = LocalDevice(
        device_id=device_id,
        display_name="Test Device",
        public_signing_key=signing_service.get_public_key_base64(),
        trust_state="trusted"
    )
    return repo.create_device(device)

@pytest.fixture
def submitted_quote():
    repo = QuoteRepository()
    quote_id = "quote-123"
    existing = repo.get_by_id(quote_id)
    if existing:
        # Reset status for test
        repo.update_status(quote_id, QuoteStatus.SUBMITTED)
        return existing
        
    quote = Quote(
        id=quote_id,
        status=QuoteStatus.SUBMITTED,
        short_summary="Test Quote"
    )
    return repo.create(quote)

def test_writeback_missing_token_rejected(client):
    """Verify that missing sync token is rejected."""
    response = client.post("/api/sync/actions", json={})
    assert response.status_code == 401

def test_writeback_invalid_token_rejected(client, setup_auth):
    """Verify that invalid sync token is rejected."""
    response = client.post(
        "/api/sync/actions", 
        headers={"X-Intake-Sync-Token": "wrong"},
        json={}
    )
    assert response.status_code == 401

def test_quote_review_start_success(
    client, 
    setup_auth, 
    sync_token, 
    signing_service, 
    registered_device, 
    submitted_quote
):
    """Verify successful QUOTE_REVIEW_START transition."""
    envelope = signing_service.sign_action(
        device_id=registered_device.device_id,
        action_kind="QUOTE_REVIEW_START",
        aggregate_type="quote",
        aggregate_id=submitted_quote.id,
        payload={}
    )
    
    response = client.post(
        "/api/sync/actions",
        headers={"X-Intake-Sync-Token": sync_token},
        content=envelope.model_dump_json()
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["new_status"] == "reviewing"
    assert data["previous_status"] == "submitted"
    
    # Verify DB state
    updated_quote = QuoteRepository().get_by_id(submitted_quote.id)
    assert updated_quote.status == QuoteStatus.REVIEWING
    
    # Verify event log
    events = EventRepository().get_for_aggregate(EventAggregateType.QUOTE, submitted_quote.id)
    assert any(e.event_type == EventType.QUOTE_REVIEW_STARTED for e in events)

def test_invalid_transition_rejected(
    client, 
    setup_auth, 
    sync_token, 
    signing_service, 
    registered_device
):
    """Verify that illegal status transitions are rejected."""
    import uuid
    repo = QuoteRepository()
    quote_id = f"draft-{uuid.uuid4()}"
    draft_quote = repo.create(Quote(id=quote_id, status=QuoteStatus.DRAFT))
    
    envelope = signing_service.sign_action(
        device_id=registered_device.device_id,
        action_kind="QUOTE_REVIEW_START",
        aggregate_type="quote",
        aggregate_id=draft_quote.id,
        payload={}
    )
    
    response = client.post(
        "/api/sync/actions",
        headers={"X-Intake-Sync-Token": sync_token},
        content=envelope.model_dump_json()
    )
    
    assert response.status_code == 400
    assert "Cannot transition from draft to reviewing" in response.text

def test_replay_attack_rejected(
    client, 
    setup_auth, 
    sync_token, 
    signing_service, 
    registered_device, 
    submitted_quote
):
    """Verify that replaying an action_id is rejected."""
    envelope = signing_service.sign_action(
        device_id=registered_device.device_id,
        action_kind="QUOTE_REVIEW_START",
        aggregate_type="quote",
        aggregate_id=submitted_quote.id,
        payload={}
    )
    
    # First time
    client.post(
        "/api/sync/actions",
        headers={"X-Intake-Sync-Token": sync_token},
        content=envelope.model_dump_json()
    )
    
    # Replay
    response = client.post(
        "/api/sync/actions",
        headers={"X-Intake-Sync-Token": sync_token},
        content=envelope.model_dump_json()
    )
    
    assert response.status_code == 403
    assert "Duplicate action_id" in response.text
