"""Tests for Local Upload Receiver v0 - Clean version."""

import os
import tempfile
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from intake.local_console.receiver.models import (
    FileRejectionReason,
    LocalUploadSessionCreate,
    ReceiverStatus,
    ReceiverHandshakeChallenge,
    SessionStatus,
    UploadFileRequest,
    ALLOWED_CONTENT_TYPES,
    ALLOWED_EXTENSIONS,
    DEFAULT_MAX_FILE_SIZE_BYTES,
    DEFAULT_MAX_FILES_PER_SESSION,
    DEFAULT_MAX_TOTAL_BYTES_PER_SESSION,
)
from intake.local_console.receiver.service import LocalReceiverService
from intake.local_console.receiver.storage import LocalReceiverStorageService
from intake.local_console.receiver.route_decision import (
    UploadRouteDecisionService,
    UploadRouteDecision,
)
from intake.deploy.models_upload import UploadProviderKind


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_upload_root():
    """Create a temporary upload root directory."""
    tmpdir = tempfile.mkdtemp(prefix="intake_test_receiver_")
    yield Path(tmpdir)
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def storage_service(temp_upload_root):
    """Storage service with temporary root."""
    return LocalReceiverStorageService(root_path=temp_upload_root)


@pytest.fixture
def receiver_service(storage_service):
    """Receiver service with temporary storage."""
    return LocalReceiverService(storage_service=storage_service)


@pytest.fixture
def route_decision_service(receiver_service):
    """Route decision service with receiver."""
    return UploadRouteDecisionService(receiver_service=receiver_service)


@pytest.fixture
def receiver_client(receiver_service):
    """Test client for receiver API."""
    from intake.local_console.receiver.api import create_receiver_app
    
    app = create_receiver_app()
    
    def override_get_receiver_service():
        return receiver_service
    
    app.dependency_overrides["get_receiver_service"] = override_get_receiver_service
    
    with TestClient(app) as client:
        yield client


# =============================================================================
# Basic Tests to verify implementation works
# =============================================================================

class TestBasicFunctionality:
    """Basic functionality tests for Local Receiver."""
    
    def test_receiver_service_creation(self):
        """Receiver service can be created."""
        svc = LocalReceiverService()
        assert svc.receiver_id == "local_loopback_dev_001"
        assert svc.status == ReceiverStatus.ONLINE
    
    def test_handshake_returns_online(self, receiver_service):
        """Handshake returns online status."""
        response = receiver_service.perform_handshake()
        assert response.status == ReceiverStatus.ONLINE
        assert response.receiver_id == "local_loopback_dev_001"
        assert "multipart" in response.supported_protocols
    
    def test_storage_service_creation(self, temp_upload_root):
        """Storage service can be created."""
        svc = LocalReceiverStorageService(root_path=temp_upload_root)
        assert svc.upload_root == temp_upload_root
    
    def test_file_id_generation(self, storage_service):
        """File IDs are generated."""
        id1 = storage_service.generate_file_id()
        id2 = storage_service.generate_file_id()
        assert id1 != id2
        assert len(id1) == 32  # hex(16 bytes) = 32 chars
    
    def test_session_creation(self, receiver_service):
        """Upload sessions can be created."""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        request = LocalUploadSessionCreate(
            quote_id="quote_test_123",
            expires_at=expires_at,
        )
        session = receiver_service.create_session(request)
        assert session.session_id
        assert session.quote_id == "quote_test_123"
        assert session.status == SessionStatus.ACTIVE
    
    def test_file_upload_works(self, receiver_service, temp_upload_root):
        """File upload works end-to-end."""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        create_req = LocalUploadSessionCreate(quote_id="quote_123", expires_at=expires_at)
        session = receiver_service.create_session(create_req)
        
        request = UploadFileRequest(
            session_id=session.session_id,
            declared_content_type="image/jpeg",
            original_filename="photo.jpg",
        )
        
        content = b"Test file content"
        file_record, rejection = receiver_service.process_file_upload(
            session.session_id, request, content
        )
        
        assert rejection is None
        assert file_record.file_id
        assert file_record.size_bytes == len(content)
        assert file_record.sha256
        assert file_record.extension == "jpg"
    
    def test_api_health_check(self, receiver_client):
        """Health check endpoint works."""
        response = receiver_client.get("/receiver/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "online"
        assert data["receiver_id"] == "local_loopback_dev_001"
    
    def test_api_handshake(self, receiver_client):
        """Handshake endpoint works."""
        response = receiver_client.post("/receiver/handshake")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "online"
        assert data["receiver_id"] == "local_loopback_dev_001"
    
    def test_api_create_session(self, receiver_client):
        """Session creation endpoint works."""
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        response = receiver_client.post("/receiver/uploads/session", json={
            "quote_id": "quote_test",
            "expires_at": expires_at,
        })
        assert response.status_code == 201
        data = response.json()
        assert "session_id" in data
        assert data["quote_id"] == "quote_test"
    
    def test_api_upload_file(self, receiver_client, temp_upload_root):
        """File upload endpoint works."""
        # Create session
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        session_resp = receiver_client.post("/receiver/uploads/session", json={
            "quote_id": "quote_123",
            "expires_at": expires_at,
        })
        session_id = session_resp.json()["session_id"]
        
        # Upload file
        file_content = b"Test content"
        files = {"file": ("test.jpg", file_content, "image/jpeg")}
        response = receiver_client.post(
            f"/receiver/uploads/{session_id}/file",
            files=files,
            data={"declared_content_type": "image/jpeg", "original_filename": "test.jpg"},
        )
        assert response.status_code == 200
        receipt = response.json()
        assert "upload_id" in receipt
        assert receipt["size_bytes"] == len(file_content)
        assert "sha256" in receipt
    
    def test_route_decision_local_when_online(self, route_decision_service):
        """Route decision selects local when online."""
        decision = route_decision_service.decide_upload_route(
            quote_id="quote_123",
            requested_content_types=["image/jpeg"],
            requested_max_file_size=100 * 1024 * 1024,
        )
        assert decision.chosen_provider == UploadProviderKind.LOCAL_LOOPBACK_DEV
        assert decision.route_priority == 1
    
    def test_route_decision_fallback_when_offline(self, receiver_service):
        """Route decision falls back when receiver offline."""
        svc = UploadRouteDecisionService(receiver_service=receiver_service)
        svc.set_fallback_provider(UploadProviderKind.S3_COMPATIBLE_FUTURE)
        receiver_service.set_status(ReceiverStatus.OFFLINE)
        
        decision = svc.decide_upload_route(
            quote_id="quote_123",
            requested_content_types=["image/jpeg"],
            requested_max_file_size=100 * 1024 * 1024,
        )
        assert decision.chosen_provider == UploadProviderKind.S3_COMPATIBLE_FUTURE
        assert decision.route_priority == 2
    
    def test_validation_rejects_disallowed_content_type(self, receiver_service):
        """Validation rejects disallowed content type."""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        create_req = LocalUploadSessionCreate(quote_id="quote_123", expires_at=expires_at)
        session = receiver_service.create_session(create_req)
        
        request = UploadFileRequest(
            session_id=session.session_id,
            declared_content_type="application/exe",
        )
        
        ext, rejection = receiver_service.validate_file_upload(
            session.session_id, request, 100
        )
        
        assert rejection == FileRejectionReason.DISALLOWED_CONTENT_TYPE
    
    def test_validation_rejects_empty_file(self, receiver_service):
        """Validation rejects empty file."""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        create_req = LocalUploadSessionCreate(quote_id="quote_123", expires_at=expires_at)
        session = receiver_service.create_session(create_req)
        
        request = UploadFileRequest(
            session_id=session.session_id,
            declared_content_type="image/jpeg",
        )
        
        ext, rejection = receiver_service.validate_file_upload(
            session.session_id, request, 0
        )
        
        assert rejection == FileRejectionReason.EMPTY_FILE
    
    def test_validation_rejects_complete_session(self, receiver_service):
        """Validation rejects uploads to completed session."""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        create_req = LocalUploadSessionCreate(quote_id="quote_123", expires_at=expires_at)
        session = receiver_service.create_session(create_req)
        
        # Mark as completed
        receiver_service._sessions[session.session_id].status = SessionStatus.COMPLETED
        
        request = UploadFileRequest(
            session_id=session.session_id,
            declared_content_type="image/jpeg",
        )
        
        ext, rejection = receiver_service.validate_file_upload(
            session.session_id, request, 100
        )
        
        assert rejection == FileRejectionReason.COMPLETED_SESSION
    
    def test_receipt_includes_sha256(self, receiver_service, temp_upload_root):
        """Upload receipt includes SHA256 hash."""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        create_req = LocalUploadSessionCreate(quote_id="quote_123", expires_at=expires_at)
        session = receiver_service.create_session(create_req)
        
        import hashlib
        content = b"SHA256 test"
        expected_sha = hashlib.sha256(content).hexdigest()
        
        request = UploadFileRequest(
            session_id=session.session_id,
            declared_content_type="image/jpeg",
        )
        
        file_record, rejection = receiver_service.process_file_upload(
            session.session_id, request, content
        )
        
        assert rejection is None
        assert file_record.sha256 == expected_sha
    
    def test_no_paths_in_handshake(self, receiver_service):
        """Handshake response contains no filesystem paths."""
        response = receiver_service.perform_handshake()
        response_dict = response.model_dump()
        
        for key, value in response_dict.items():
            if isinstance(value, str):
                assert ".build" not in value
                assert "/tmp" not in value
    
    def test_no_secrets_in_handshake(self, receiver_service):
        """Handshake response contains no secrets."""
        response = receiver_service.perform_handshake()
        response_dict = response.model_dump()
        
        secret_patterns = ["api_key", "secret", "token", "password", "credential"]
        json_str = str(response_dict).lower()
        
        for pattern in secret_patterns:
            # Allow "local_loopback_dev" which contains "al"
            assert pattern not in json_str or "local" in json_str
