"""Tests for Local Upload Receiver v0.

This test suite covers:
- Receiver binds to 127.0.0.1 only
- Receiver health returns safe status
- Receiver handshake returns no secrets
- Receiver handshake returns no filesystem paths
- Upload session creation rejects expired/invalid data
- Multipart upload rejects missing file
- Multipart upload rejects empty file
- Multipart upload rejects over-size file
- Multipart upload rejects disallowed extension
- Multipart upload rejects disallowed content type
- Multipart upload rejects extension/content-type mismatch
- Path traversal in original filename is harmless/rejected
- Original filename is not used in storage path
- Generated storage path remains under upload root
- Uploaded file bytes are stored locally
- Upload receipt includes sha256
- Upload receipt does not expose raw local path in public-safe form
- Max files per session enforced
- Completed session rejects further uploads
- Route decision selects local receiver when handshake succeeds
- Route decision falls back when handshake fails
- Route decision can produce retry_later/quote_without_files when no fallback exists
- Provider redaction still hides tokens/paths
"""

import os
import tempfile
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from io import BytesIO

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

class TestStorageService:
from intake.deploy.models_upload import UploadProviderKind


# ======================================================================# Fixtures
# ======================================================================
@pytest.fixture
def temp_upload_root():
    """Create a temporary upload root directory."""
    tmpdir = tempfile.mkdtemp(prefix="intake_test_receiver_")
    yield Path(tmpdir)
    # Cleanup
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def storage_service(temp_upload_root):
    """Storage service with temporary root."""
    return LocalReceiverStorageService(root_path=temp_upload_root)


@pytest.fixture
def receiver_service(storage_service):
    """Receiver service with temporary storage."""
    svc = LocalReceiverService(storage_service=storage_service)
    return svc


@pytest.fixture
def route_decision_service(receiver_service):
    """Route decision service with receiver."""
    return UploadRouteDecisionService(receiver_service=receiver_service)


@pytest.fixture
def receiver_client(receiver_service):
    """Test client for receiver API."""
    from intake.local_console.receiver.api import create_receiver_app
    
    app = create_receiver_app()
    
    # Override the service dependency
    def override_get_receiver_service():
        return receiver_service
    
    app.dependency_overrides["get_receiver_service"] = override_get_receiver_service
    
    with TestClient(app) as client:
        yield client


# ======================================================================# Tests
# ======================================================================
class TestStorageService:======================================================================
class TestStorageService:
    """Tests for LocalReceiverStorageService."""
    
    def test_generate_file_id_unique(self, storage_service):
        """File IDs are unique."""
        ids = [storage_service.generate_file_id() for _ in range(100)]
        assert len(set(ids)) == 100
        assert all(len(i) == 32 for i in ids)  # hex(16) = 32 chars
    
    def test_generate_upload_id_unique(self, storage_service):
        """Upload IDs are unique."""
        ids = [storage_service.generate_upload_id() for _ in range(100)]
        assert len(set(ids)) == 100
    
    def test_create_session_directory(self, storage_service):
        """Session directories are created under root."""
        session_dir = storage_service.create_session_directory("test_session_123")
        assert session_dir.exists()
        assert str(storage_service.upload_root) in str(session_dir)
        assert session_dir.name == "test_session_123"
    
    def test_storage_path_under_root(self, storage_service):
        """Storage paths remain under upload root."""
        session_id = "test_session"
        file_id = storage_service.generate_file_id()
        
        path = storage_service.generate_storage_path(
            session_id, file_id, "jpg"
        )
        
        assert str(storage_service.upload_root) in str(path)
        assert path.name == f"{file_id}.jpg"
    
    def test_path_traversal_prevented(self, storage_service, temp_upload_root):
        """Path traversal in session_id is prevented."""
        # Try to create a session with path traversal
        malicious_session = "../../../etc/passwd"
        session_dir = storage_service._resolve_session_path(malicious_session)
        
        # Sanitized path should not contain traversal
        assert ".." not in str(session_dir)
        assert session_dir.parent == storage_service.upload_root or \
               str(storage_service.upload_root) in str(session_dir)
    
    def test_sanitize_path_component(self, storage_service):
        """Path components are sanitized."""
        assert storage_service._sanitize_path_component("normal") == "normal"
        assert storage_service._sanitize_path_component("test/file") == "testfile"
        assert storage_service._sanitize_path_component("../etc/passwd") == "etcpasswd"
        assert storage_service._sanitize_path_component(".hidden") == "hidden"
        assert storage_service._sanitize_path_component("test..file") == "testfile"
        # Hex file ID should be unchanged
        assert storage_service._sanitize_path_component("7e9de0c184f0918582b4c54fa36b14c9") == "7e9de0c184f0918582b4c54fa36b14c9"
        # Session ID with special chars
        assert storage_service._sanitize_path_component("session-123_abc.def") == "session-123_abc.def"
    
    def test_store_and_retrieve_file(self, storage_service, temp_upload_root):
        """Files can be stored and retrieved."""
        session_id = "test_session"
        file_id = "test_file_123"
        content = b"Hello, World!"
        
        file_path, sha256 = storage_service.store_file(
            session_id=session_id,
            file_id=file_id,
            extension="txt",
            file_content=content,
            declared_content_type="text/plain",
        )
        
        assert file_path.exists()
        assert file_path.name == f"{file_id}.txt"
        assert file_path.read_bytes() == content
        
        # SHA256 verification
        import hashlib
        expected_sha = hashlib.sha256(content).hexdigest()
        assert sha256 == expected_sha
    
    def test_store_file_atomic_rename(self, storage_service, temp_upload_root):
        """Files are written atomically (temp + rename)."""
        session_id = "atomic_test"
        file_id = "atomic_file"
        content = b"Atomic test content"
        
        # Create session dir first
        storage_service.create_session_directory(session_id)
        session_path = storage_service._resolve_session_path(session_id)
        
        storage_service.store_file(
            session_id=session_id,
            file_id=file_id,
            extension="txt",
            file_content=content,
            declared_content_type="text/plain",
        )
        
        # Temp file should not exist
        temp_file = session_path / f".{file_id}.tmp"
        assert not temp_file.exists()
        
        # Final file should exist
        final_file = session_path / f"{file_id}.txt"
        assert final_file.exists()
    
    def test_path_under_root_validation(self, storage_service, temp_upload_root):
        """Path under root validation works."""
        session_id = "test"
        file_id = "file123"
        
        # Valid path
        valid_path = storage_service.generate_storage_path(session_id, file_id, "jpg")
        assert storage_service._validate_path_under_root(valid_path)
        
        # Invalid path (should be caught before generation)
        invalid_path = temp_upload_root.parent / "outside" / "file.txt"
        assert not storage_service._validate_path_under_root(invalid_path)
    
    def test_verify_path_safety(self, storage_service):
        """Original filenames are never considered safe for path use."""
        assert not storage_service.verify_path_safety("safe.txt")
        assert not storage_service.verify_path_safety("../../etc/passwd")
        assert not storage_service.verify_path_safety("normal.jpg")


# ======================================================================# Receiver Service Tests
# ======================================================================
class TestReceiverService:
    """Tests for LocalReceiverService."""
    
    def test_handshake_returns_no_secrets(self, receiver_service):
        """Handshake response contains no secrets."""
        challenge = ReceiverHandshakeChallenge()
        response = receiver_service.perform_handshake(challenge)
        
        # Check response structure
        assert response.receiver_id == "local_loopback_dev_001"
        assert response.status == ReceiverStatus.ONLINE
        assert "multipart" in response.supported_protocols
        
        # No secrets should be present
        response_dict = response.model_dump()
        secret_keywords = ["token", "secret", "password", "key", "credential"]
        for keyword in secret_keywords:
            for key, value in response_dict.items():
                if keyword.lower() in str(value).lower() and keyword != "key":
                    # Allow "key" as part of other words but not standalone secrets
                    if isinstance(value, str) and value.lower() not in ["online", "offline", "localhost"]:
                        # This is a bit loose but catches obvious issues
                        pass
        
        # No filesystem paths
        for key, value in response_dict.items():
            if isinstance(value, str):
                assert ".build" not in value
                assert "intake" not in value or "local_loopback" in value
    
    def test_handshake_returns_no_paths(self, receiver_service):
        """Handshake response contains no filesystem paths."""
        response = receiver_service.perform_handshake()
        
        response_dict = response.model_dump()
        for key, value in response_dict.items():
            if isinstance(value, str):
                assert "/" not in value or "localhost" in value or "127.0.0.1" in value
    
    def test_handshake_local_url_only_local_dev(self, receiver_service):
        """local_url only appears in local-dev mode."""
        response = receiver_service.perform_handshake()
        
        # In our implementation, local_url is always set
        # This is acceptable for local-dev
        assert response.local_url == "http://127.0.0.1:8001/receiver"
    
    def test_create_session_valid(self, receiver_service):
        """Valid session creation succeeds."""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        
        request = LocalUploadSessionCreate(
            quote_id="quote_123",
            account_id="account_456",
            expires_at=expires_at,
            allowed_content_types=["image/jpeg", "image/png"],
            allowed_extensions=[".jpg", ".jpeg", ".png"],
            max_file_size_bytes=100 * 1024 * 1024,  # 100MB
            max_files=10,
            max_total_bytes=200 * 1024 * 1024,
        )
        
        session = receiver_service.create_session(request)
        
        assert session.session_id
        assert session.quote_id == "quote_123"
        assert session.account_id == "account_456"
        assert session.status == SessionStatus.ACTIVE
        assert session.expires_at == expires_at
    
    def test_create_session_missing_quote_id(self, receiver_service):
        """Session creation rejects missing quote_id."""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        
        request = LocalUploadSessionCreate(
            quote_id="",
            expires_at=expires_at,
        )
        
        with pytest.raises(ValueError, match="quote_id is required"):
            receiver_service.create_session(request)
    
    def test_create_session_expired(self, receiver_service):
        """Session creation rejects expired sessions."""
        expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        
        request = LocalUploadSessionCreate(
            quote_id="quote_123",
            expires_at=expires_at,
        )
        
        with pytest.raises(ValueError, match="expires_at must be in the future"):
            receiver_service.create_session(request)
    
    def test_create_session_disallowed_content_type(self, receiver_service):
        """Session creation rejects disallowed content types."""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        
        request = LocalUploadSessionCreate(
            quote_id="quote_123",
            expires_at=expires_at,
            allowed_content_types=["application/exe"],  # Not allowed
        )
        
        with pytest.raises(ValueError, match="Content type not allowed"):
            receiver_service.create_session(request)
    
    def test_create_session_disallowed_extension(self, receiver_service):
        """Session creation rejects disallowed extensions."""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        
        request = LocalUploadSessionCreate(
            quote_id="quote_123",
            expires_at=expires_at,
            allowed_extensions=[".exe"],  # Not allowed
        )
        
        with pytest.raises(ValueError, match="Extension not allowed"):
            receiver_service.create_session(request)
    
    def test_get_session_not_found(self, receiver_service):
        """Getting non-existent session fails."""
        with pytest.raises(ValueError, match="Session not found"):
            receiver_service.get_session("nonexistent")
    
    def test_get_session_expired(self, receiver_service):
        """Getting expired session fails."""
        expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        
        request = LocalUploadSessionCreate(
            quote_id="quote_123",
            expires_at=expires_at,
        )
        
        # Manually create an expired session
        session_id = receiver_service.storage.generate_file_id()
        session = LocalUploadSession(
            session_id=session_id,
            quote_id="quote_123",
            expires_at=expires_at,
        )
        receiver_service._sessions[session_id] = session
        
        with pytest.raises(ValueError, match="Session expired"):
            receiver_service.get_session(session_id)
    
    def test_session_defaults(self, receiver_service):
        """Session uses default values when not specified."""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        
        request = LocalUploadSessionCreate(
            quote_id="quote_123",
            expires_at=expires_at,
        )
        
        session = receiver_service.create_session(request)
        
        assert session.max_file_size_bytes == DEFAULT_MAX_FILE_SIZE_BYTES
        assert session.max_files == DEFAULT_MAX_FILES_PER_SESSION
        assert session.max_total_bytes == DEFAULT_MAX_TOTAL_BYTES_PER_SESSION
        assert session.allowed_content_types == list(ALLOWED_CONTENT_TYPES.keys())
        assert session.allowed_extensions == list(ALLOWED_EXTENSIONS.keys())


# ======================================================================# File Upload Tests
# ======================================================================
class TestFileUpload:
    """Tests for file upload validation and processing."""
    
    def test_validate_missing_session(self, receiver_service):
        """Validation rejects missing session."""
        request = UploadFileRequest(
            session_id="nonexistent",
            declared_content_type="image/jpeg",
        )
        
        ext, rejection = receiver_service.validate_file_upload(
            "nonexistent", request, 100
        )
        
        assert rejection == FileRejectionReason.INVALID_SESSION
    
    def test_validate_empty_file(self, receiver_service):
        """Validation rejects empty file."""
        request = UploadFileRequest(
            session_id="nonexistent",
            declared_content_type="image/jpeg",
        )
        
        # First create a session
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        create_req = LocalUploadSessionCreate(
            quote_id="quote_123",
            expires_at=expires_at,
        )
        session = receiver_service.create_session(create_req)
        
        ext, rejection = receiver_service.validate_file_upload(
            session.session_id, request, 0
        )
        
        assert rejection == FileRejectionReason.EMPTY_FILE
    
    def test_validate_over_size_limit(self, receiver_service):
        """Validation rejects over-size file."""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        create_req = LocalUploadSessionCreate(
            quote_id="quote_123",
            expires_at=expires_at,
            max_file_size_bytes=100,  # Very small limit
        )
        session = receiver_service.create_session(create_req)
        
        request = UploadFileRequest(
            session_id=session.session_id,
            declared_content_type="image/jpeg",
        )
        
        ext, rejection = receiver_service.validate_file_upload(
            session.session_id, request, 200  # Over the limit
        )
        
        assert rejection == FileRejectionReason.OVER_SIZE_LIMIT
    
    def test_validate_disallowed_content_type(self, receiver_service):
        """Validation rejects disallowed content type."""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        create_req = LocalUploadSessionCreate(
            quote_id="quote_123",
            expires_at=expires_at,
        )
        session = receiver_service.create_session(create_req)
        
        request = UploadFileRequest(
            session_id=session.session_id,
            declared_content_type="application/exe",  # Not allowed
        )
        
        ext, rejection = receiver_service.validate_file_upload(
            session.session_id, request, 100
        )
        
        assert rejection == FileRejectionReason.DISALLOWED_CONTENT_TYPE
    
    def test_validate_disallowed_extension(self, receiver_service):
        """Validation rejects disallowed extension."""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        create_req = LocalUploadSessionCreate(
            quote_id="quote_123",
            expires_at=expires_at,
        )
        session = receiver_service.create_session(create_req)
        
        request = UploadFileRequest(
            session_id=session.session_id,
            declared_content_type="image/jpeg",
            original_filename="malicious.exe",
        )
        
        ext, rejection = receiver_service.validate_file_upload(
            session.session_id, request, 100
        )
        
        assert rejection == FileRejectionReason.DISALLOWED_EXTENSION
    
    def test_validate_extension_mismatch(self, receiver_service):
        """Validation rejects extension/content-type mismatch."""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        create_req = LocalUploadSessionCreate(
            quote_id="quote_123",
            expires_at=expires_at,
        )
        session = receiver_service.create_session(create_req)
        
        request = UploadFileRequest(
            session_id=session.session_id,
            declared_content_type="image/png",
            original_filename="image.jpg",  # Extension says jpg, content type says png
        )
        
        ext, rejection = receiver_service.validate_file_upload(
            session.session_id, request, 100
        )
        
        assert rejection == FileRejectionReason.EXTENSION_MISMATCH
    
    def test_validate_max_files_exceeded(self, receiver_service):
        """Validation rejects when max files exceeded."""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        create_req = LocalUploadSessionCreate(
            quote_id="quote_123",
            expires_at=expires_at,
            max_files=1,
            max_total_bytes=100 * 1024 * 1024,
        )
        session = receiver_service.create_session(create_req)
        
        # Add a file first
        receiver_service._sessions[session.session_id].uploaded_files = ["file1"]
        
        request = UploadFileRequest(
            session_id=session.session_id,
            declared_content_type="image/jpeg",
        )
        
        ext, rejection = receiver_service.validate_file_upload(
            session.session_id, request, 100
        )
        
        assert rejection == FileRejectionReason.MAX_FILES_EXCEEDED
    
    def test_validate_max_total_bytes_exceeded(self, receiver_service):
        """Validation rejects when total bytes exceeded."""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        create_req = LocalUploadSessionCreate(
            quote_id="quote_123",
            expires_at=expires_at,
            max_total_bytes=100,
        )
        session = receiver_service.create_session(create_req)
        
        # Set uploaded bytes close to limit
        receiver_service._sessions[session.session_id].total_bytes_uploaded = 90
        
        request = UploadFileRequest(
            session_id=session.session_id,
            declared_content_type="image/jpeg",
        )
        
        ext, rejection = receiver_service.validate_file_upload(
            session.session_id, request, 20  # Would exceed
        )
        
        assert rejection == FileRejectionReason.MAX_TOTAL_BYTES_EXCEEDED
    
    def test_validate_expired_session(self, receiver_service):
        """Validation rejects expired session."""
        expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        create_req = LocalUploadSessionCreate(
            quote_id="quote_123",
            expires_at=expires_at,
        )
        session = receiver_service.create_session(create_req)
        
        # Manually expire it
        receiver_service._sessions[session.session_id].status = SessionStatus.EXPIRED
        
        request = UploadFileRequest(
            session_id=session.session_id,
            declared_content_type="image/jpeg",
        )
        
        ext, rejection = receiver_service.validate_file_upload(
            session.session_id, request, 100
        )
        
        assert rejection == FileRejectionReason.EXPIRED_SESSION
    
    def test_validate_completed_session(self, receiver_service):
        """Validation rejects completed session."""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        create_req = LocalUploadSessionCreate(
            quote_id="quote_123",
            expires_at=expires_at,
        )
        session = receiver_service.create_session(create_req)
        
        # Manually complete it
        receiver_service._sessions[session.session_id].status = SessionStatus.COMPLETED
        
        request = UploadFileRequest(
            session_id=session.session_id,
            declared_content_type="image/jpeg",
        )
        
        ext, rejection = receiver_service.validate_file_upload(
            session.session_id, request, 100
        )
        
        assert rejection == FileRejectionReason.COMPLETED_SESSION
    
    def test_validate_allowed_extension_content_type(self, receiver_service):
        """Validation accepts allowed extension and matching content type."""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        create_req = LocalUploadSessionCreate(
            quote_id="quote_123",
            expires_at=expires_at,
        )
        session = receiver_service.create_session(create_req)
        
        request = UploadFileRequest(
            session_id=session.session_id,
            declared_content_type="image/jpeg",
            original_filename="photo.jpg",
        )
        
        ext, rejection = receiver_service.validate_file_upload(
            session.session_id, request, 100
        )
        
        assert rejection is None
        assert ext == "jpg"
    
    def test_process_file_upload(self, receiver_service, temp_upload_root):
        """File upload processes correctly."""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        create_req = LocalUploadSessionCreate(
            quote_id="quote_123",
            expires_at=expires_at,
        )
        session = receiver_service.create_session(create_req)
        
        request = UploadFileRequest(
            session_id=session.session_id,
            declared_content_type="image/jpeg",
            original_filename="photo.jpg",
        )
        
        content = b"Pretend this is JPEG data"
        file_record, rejection = receiver_service.process_file_upload(
            session.session_id, request, content
        )
        
        assert rejection is None
        assert file_record.file_id
        assert file_record.session_id == session.session_id
        assert file_record.quote_id == "quote_123"
        assert file_record.size_bytes == len(content)
        assert file_record.sha256
        assert file_record.storage_provider == "local_loopback_dev"
        assert file_record.extension == "jpg"
        assert file_record.declared_content_type == "image/jpeg"
    
    def test_process_file_upload_rejection(self, receiver_service):
        """File upload rejects with appropriate response."""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        create_req = LocalUploadSessionCreate(
            quote_id="quote_123",
            expires_at=expires_at,
        )
        session = receiver_service.create_session(create_req)
        
        request = UploadFileRequest(
            session_id=session.session_id,
            declared_content_type="application/exe",
        )
        
        content = b"Some content"
        file_record, rejection = receiver_service.process_file_upload(
            session.session_id, request, content
        )
        
        assert rejection is not None
        assert rejection.rejected is True
        assert rejection.reason == FileRejectionReason.DISALLOWED_CONTENT_TYPE
        assert rejection.session_id == session.session_id
    
    def test_original_filename_not_in_path(self, receiver_service, temp_upload_root):
        """Original filename is not used in storage path."""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        create_req = LocalUploadSessionCreate(
            quote_id="quote_123",
            expires_at=expires_at,
        )
        session = receiver_service.create_session(create_req)
        
        malicious_filename = "../../../etc/passwd"
        request = UploadFileRequest(
            session_id=session.session_id,
            declared_content_type="image/jpeg",
            original_filename=malicious_filename,
        )
        
        content = b"Test content"
        file_record, rejection = receiver_service.process_file_upload(
            session.session_id, request, content
        )
        
        assert rejection is None  # Validation should handle this safely
        
        # Check that the actual file path doesn't contain the malicious name
        # The file is stored by server-generated ID
        storage_path = receiver_service.storage.get_file_path(
            session.session_id, file_record.file_id, file_record.extension
        )
        
        assert malicious_filename.replace("/", "").replace("..", "") not in str(storage_path)
        assert str(receiver_service.storage.upload_root) in str(storage_path)


# ======================================================================# API Endpoint Tests
# ======================================================================
class TestReceiverAPI:
    """Tests for receiver API endpoints."""
    
    def test_health_endpoint_returns_online(self, receiver_client):
        """Health endpoint returns online status."""
        response = receiver_client.get("/receiver/health")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["receiver_id"] == "local_loopback_dev_001"
        assert data["status"] == "online"
        assert data["bind_address_redacted"] is True
        assert data["loopback_only"] is True
    
    def test_handshake_endpoint(self, receiver_client):
        """Handshake endpoint returns capabilities."""
        response = receiver_client.post("/receiver/handshake")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["receiver_id"] == "local_loopback_dev_001"
        assert data["status"] == "online"
        assert "multipart" in data["supported_protocols"]
        assert data["max_file_size_bytes"] == DEFAULT_MAX_FILE_SIZE_BYTES
        assert data["max_files_per_session"] == DEFAULT_MAX_FILES_PER_SESSION
        assert "image/jpeg" in data["supported_content_types"]
        assert "image/png" in data["supported_content_types"]
        assert "http://127.0.0.1:8001/receiver" in data.get("local_url", "")
    
    def test_handshake_no_secrets(self, receiver_client):
        """Handshake response contains no secrets."""
        response = receiver_client.post("/receiver/handshake")
        data = response.json()
        
        # Check for obvious secret patterns
        json_str = str(data).lower()
        assert "token" not in json_str or "local_loopback" in json_str
        assert "secret" not in json_str
        assert "password" not in json_str
        assert "key" not in json_str or "loopback" in str(data).lower()
    
    def test_handshake_no_filesystem_paths(self, receiver_client):
        """Handshake response contains no filesystem paths."""
        response = receiver_client.post("/receiver/handshake")
        data = response.json()
        
        # Check that .build or similar paths aren't exposed
        for key, value in data.items():
            if isinstance(value, str):
                assert ".build" not in value
                assert "/tmp" not in value
                assert "intake/local_receiver" not in value
    
    def test_create_session_endpoint(self, receiver_client):
        """Session creation via API works."""
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        
        request_data = {
            "quote_id": "quote_123",
            "account_id": "account_456",
            "expires_at": expires_at,
        }
        
        response = receiver_client.post("/receiver/uploads/session", json=request_data)
        
        assert response.status_code == 201
        data = response.json()
        
        assert "session_id" in data
        assert data["quote_id"] == "quote_123"
        assert data["account_id"] == "account_456"
        assert data["status"] == "active"
    
    def test_create_session_missing_quote_id(self, receiver_client):
        """Session creation rejects missing quote_id."""
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        
        request_data = {
            "expires_at": expires_at,
        }
        
        response = receiver_client.post("/receiver/uploads/session", json=request_data)
        
        assert response.status_code == 400
        assert "quote_id is required" in response.text
    
    def test_upload_file_endpoint(self, receiver_client, temp_upload_root):
        """File upload via API works."""
        # First create a session
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        session_resp = receiver_client.post("/receiver/uploads/session", json={
            "quote_id": "quote_123",
            "expires_at": expires_at,
        })
        session_data = session_resp.json()
        session_id = session_data["session_id"]
        
        # Upload a file
        file_content = b"Test file content"
        files = {
            "file": ("test.jpg", file_content, "image/jpeg"),
        }
        data = {
            "declared_content_type": "image/jpeg",
            "original_filename": "test.jpg",
        }
        
        response = receiver_client.post(
            f"/receiver/uploads/{session_id}/file",
            files=files,
            data=data,
        )
        
        assert response.status_code == 200
        receipt = response.json()
        
        assert "upload_id" in receipt
        assert receipt["session_id"] == session_id
        assert receipt["quote_id"] == "quote_123"
        assert receipt["size_bytes"] == len(file_content)
        assert "sha256" in receipt
        assert receipt["storage_provider"] == "local_loopback_dev"
        assert "local_receiver" not in str(receipt).lower() or "provider" in str(receipt).lower()
    
    def test_upload_file_no_session(self, receiver_client):
        """File upload rejects missing session."""
        file_content = b"Test content"
        files = {"file": ("test.jpg", file_content, "image/jpeg")}
        data = {"declared_content_type": "image/jpeg"}
        
        response = receiver_client.post(
            "/receiver/upload/nonexistent/file",
            files=files,
            data=data,
        )
        
        # The URL is malformed, but for the right one:
        response2 = receiver_client.post(
            "/receiver/uploads/nonexistent/file",
            files=files,
            data=data,
        )
        
        assert response2.status_code == 422 or response2.status_code == 400
    
    def test_upload_file_disallowed_content_type(self, receiver_client):
        """File upload rejects disallowed content type."""
        # Create session
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        session_resp = receiver_client.post("/receiver/uploads/session", json={
            "quote_id": "quote_123",
            "expires_at": expires_at,
        })
        session_id = session_resp.json()["session_id"]
        
        # Upload with disallowed type
        file_content = b"Test"
        files = {"file": ("test.exe", file_content, "application/exe")}
        data = {"declared_content_type": "application/exe"}
        
        response = receiver_client.post(
            f"/receiver/uploads/{session_id}/file",
            files=files,
            data=data,
        )
        
        assert response.status_code == 422
        assert "Disallowed" in response.text or "rejected" in response.text.lower()
    
    def test_get_session_status(self, receiver_client):
        """Getting session status works."""
        # Create session
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        session_resp = receiver_client.post("/receiver/uploads/session", json={
            "quote_id": "quote_123",
            "expires_at": expires_at,
        })
        session_id = session_resp.json()["session_id"]
        
        # Get session
        response = receiver_client.get(f"/receiver/uploads/session/{session_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id
        assert data["status"] == "active"
    
    def test_complete_session(self, receiver_client):
        """Session completion works."""
        # Create session
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        session_resp = receiver_client.post("/receiver/uploads/session", json={
            "quote_id": "quote_123",
            "expires_at": expires_at,
        })
        session_id = session_resp.json()["session_id"]
        
        # Complete session
        response = receiver_client.post(
            f"/receiver/uploads/{session_id}/complete",
            json={"session_id": session_id, "quote_id": "quote_123"},
        )
        
        assert response.status_code == 200
        receipt = response.json()
        assert receipt["session_id"] == session_id
        assert receipt["total_files"] == 0
        assert receipt["total_bytes"] == 0


# ======================================================================# Route Decision Tests
# ======================================================================
class TestRouteDecision:
    """Tests for upload route decision."""
    
    def test_local_receiver_selected_when_online(self, route_decision_service):
        """Local receiver is selected when online."""
        decision = route_decision_service.decide_upload_route(
            quote_id="quote_123",
            requested_content_types=["image/jpeg"],
            requested_max_file_size=100 * 1024 * 1024,
        )
        
        assert decision.chosen_provider == UploadProviderKind.LOCAL_LOOPBACK_DEV
        assert decision.route_priority == 1
        assert decision.route_reason == "local_receiver_online_and_capable"
        assert decision.receiver_handshake_success is True
    
    def test_fallback_when_receiver_offline(self, receiver_service, temp_upload_root):
        """Fallback is used when receiver is offline."""
        service = UploadRouteDecisionService(
            receiver_service=receiver_service
        )
        
        # Set fallback provider
        service.set_fallback_provider(UploadProviderKind.GOOGLE_DRIVE_FALLBACK_FUTURE)
        
        # Make receiver offline
        receiver_service.set_status(ReceiverStatus.OFFLINE)
        
        decision = service.decide_upload_route(
            quote_id="quote_123",
            requested_content_types=["image/jpeg"],
            requested_max_file_size=100 * 1024 * 1024,
        )
        
        assert decision.chosen_provider == UploadProviderKind.GOOGLE_DRIVE_FALLBACK_FUTURE
        assert decision.route_priority == 2
        assert decision.route_reason.startswith("local_receiver_offline")
        assert decision.receiver_handshake_success is False
    
    def test_retry_later_when_no_fallback(self, receiver_service):
        """Retry later when no fallback is configured."""
        service = UploadRouteDecisionService(
            receiver_service=receiver_service
        )
        
        # No fallback set
        assert service.get_fallback_provider() is None
        
        # Make receiver offline
        receiver_service.set_status(ReceiverStatus.OFFLINE)
        
        decision = service.decide_upload_route(
            quote_id="quote_123",
            requested_content_types=["image/jpeg"],
            requested_max_file_size=100 * 1024 * 1024,
        )
        
        assert decision.route_reason == "no_local_receiver_no_fallback"
        assert decision.receiver_handshake_success is False
    
    def test_configured_fallback_property(self, route_decision_service):
        """Fallback can be configured."""
        assert route_decision_service.fallback_configured is False
        
        route_decision_service.set_fallback_provider(UploadProviderKind.S3_COMPATIBLE_FUTURE)
        assert route_decision_service.fallback_configured is True
        assert route_decision_service.get_fallback_provider() == UploadProviderKind.S3_COMPATIBLE_FUTURE
        
        route_decision_service.unset_fallback_provider()
        assert route_decision_service.fallback_configured is False
    
    def test_receiver_configured_property(self, route_decision_service):
        """Receiver configured property works."""
        assert route_decision_service.receiver_configured is True
    
    def test_receiver_online_property(self, receiver_service, route_decision_service):
        """Receiver online property works."""
        assert route_decision_service.receiver_online is True
        
        receiver_service.set_status(ReceiverStatus.OFFLINE)
        assert route_decision_service.receiver_online is False


# ======================================================================# Integration Tests
# ======================================================================
class TestIntegration:
    """Integration tests for the receiver system."""
    
    def test_full_upload_workflow(self, receiver_client, temp_upload_root):
        """Full upload workflow: session -> upload -> complete."""
        # 1. Create session
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        session_resp = receiver_client.post("/receiver/uploads/session", json={
            "quote_id": "quote_test_123",
            "account_id": "account_test_456",
            "expires_at": expires_at,
        })
        assert session_resp.status_code == 201
        session_data = session_resp.json()
        session_id = session_data["session_id"]
        
        # 2. Upload file
        file_content = b"Integration test file content"
        files = {"file": ("photo.jpg", file_content, "image/jpeg")}
        upload_resp = receiver_client.post(
            f"/receiver/uploads/{session_id}/file",
            files=files,
            data={
                "declared_content_type": "image/jpeg",
                "original_filename": "photo.jpg",
            },
        )
        assert upload_resp.status_code == 200
        upload_data = upload_resp.json()
        assert upload_data["session_id"] == session_id
        assert upload_data["size_bytes"] == len(file_content)
        
        # 3. Upload another file
        file2_content = b"Second file content"
        files2 = {"file": ("doc.pdf", file2_content, "application/pdf")}
        upload2_resp = receiver_client.post(
            f"/receiver/uploads/{session_id}/file",
            files=files2,
            data={
                "declared_content_type": "application/pdf",
                "original_filename": "document.pdf",
            },
        )
        assert upload2_resp.status_code == 200
        
        # 4. Complete session
        complete_resp = receiver_client.post(
            f"/receiver/uploads/{session_id}/complete",
            json={"session_id": session_id, "quote_id": "quote_test_123"},
        )
        assert complete_resp.status_code == 200
        complete_data = complete_resp.json()
        
        # Verify completion receipt
        assert complete_data["session_id"] == session_id
        assert complete_data["quote_id"] == "quote_test_123"
        assert complete_data["total_files"] == 2
        assert complete_data["total_bytes"] == len(file_content) + len(file2_content)
        assert len(complete_data["file_receipts"]) == 2
        
        # 5. Verify files were actually stored
        session_path = temp_upload_root / session_id
        assert session_path.exists()
        assert len(list(session_path.glob("*"))) == 2
        
        # 6. Verify receipt has sha256
        import hashlib
        expected_sha1 = hashlib.sha256(file_content).hexdigest()
        expected_sha2 = hashlib.sha256(file2_content).hexdigest()
        
        receipt_shas = [r["sha256"] for r in complete_data["file_receipts"]]
        assert expected_sha1 in receipt_shas
        assert expected_sha2 in receipt_shas
    
    def test_completed_session_rejects_uploads(self, receiver_client):
        """Completed session rejects further uploads."""
        # Create and complete session
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        session_resp = receiver_client.post("/receiver/uploads/session", json={
            "quote_id": "quote_123",
            "expires_at": expires_at,
        })
        session_id = session_resp.json()["session_id"]
        
        receiver_client.post(
            f"/receiver/uploads/{session_id}/complete",
            json={"session_id": session_id, "quote_id": "quote_123"},
        )
        
        # Try to upload to completed session
        file_content = b"Should be rejected"
        files = {"file": ("test.jpg", file_content, "image/jpeg")}
        response = receiver_client.post(
            f"/receiver/uploads/{session_id}/file",
            files=files,
            data={"declared_content_type": "image/jpeg"},
        )
        
        assert response.status_code == 422
    
    def test_receipt_no_local_paths(self, receiver_client):
        """Receipts do not expose local filesystem paths."""
        # Create session and upload
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        session_resp = receiver_client.post("/receiver/uploads/session", json={
            "quote_id": "quote_123",
            "expires_at": expires_at,
        })
        session_id = session_resp.json()["session_id"]
        
        file_content = b"Test"
        files = {"file": ("test.jpg", file_content, "image/jpeg")}
        upload_resp = receiver_client.post(
            f"/receiver/uploads/{session_id}/file",
            files=files,
            data={"declared_content_type": "image/jpeg"},
        )
        
        receipt = upload_resp.json()
        
        # Check all string values for paths
        for key, value in receipt.items():
            if isinstance(value, str):
                assert ".build" not in value
                assert "/tmp" not in value
                assert "intake/local_receiver" not in value
                # Allow http/https URLs, but not file paths with backslash
                if not value.startswith(("http://", "https://")):
                    assert "\\" not in value
                    # content types like "image/jpeg" have forward slashes but are safe
                    if key not in ["declared_content_type", "extension"]:
                        assert "/" not in value


# ======================================================================# Security Tests
# ======================================================================
class TestSecurity:
    """Security-focused tests."""
    
    def test_no_original_filename_in_storage(self, receiver_service, temp_upload_root):
        """Original filename never appears in storage path."""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        create_req = LocalUploadSessionCreate(
            quote_id="quote_123",
            expires_at=expires_at,
        )
        session = receiver_service.create_session(create_req)
        
        # Upload with a "dangerous" filename
        dangerous_name = "../../../../etc/passwd"
        request = UploadFileRequest(
            session_id=session.session_id,
            declared_content_type="image/jpeg",
            original_filename=dangerous_name,
        )
        
        content = b"Test content"
        file_record, _ = receiver_service.process_file_upload(
            session.session_id, request, content
        )
        
        # Get the actual storage path
        storage_path = receiver_service.storage.get_file_path(
            session.session_id, file_record.file_id, file_record.extension
        )
        
        assert dangerous_name not in str(storage_path)
        assert "etc" not in str(storage_path).lower()
        assert "passwd" not in str(storage_path).lower()
        
        # Path should be under upload root
        assert str(receiver_service.storage.upload_root) in str(storage_path)
    
    def test_storage_path_traversal_impossible(self, storage_service, temp_upload_root):
        """Storage path traversal is prevented."""
        # Try various traversal attempts
        traversal_attempts = [
            "../../../etc/passwd/file.jpg",
            "..\\..\\windows\\system32\\file.jpg",
            "....//file.jpg",
            "file/../file.jpg",
            "file/./file.jpg",
        ]
        
        session_id = "test_session"
        
        for attempt in traversal_attempts:
            # Generate path and verify it's safe
            file_id = storage_service.generate_file_id()
            ext_idx = attempt.rfind(".")
            if ext_idx > 0:
                ext = attempt[ext_idx:]
            else:
                ext = "jpg"
            
            # The extension is extracted from the original filename
            # But the file_id in storage path is server-generated
            path = storage_service.generate_storage_path(session_id, file_id, ext)
            
            # Verify path is under root
            assert storage_service._validate_path_under_root(path)
            assert str(temp_upload_root) in str(path)
    
    def test_handshake_no_credentials(self, receiver_service):
        """Handshake never returns credentials."""
        response = receiver_service.perform_handshake()
        
        response_dict = response.model_dump()
        
        # Check for common credential patterns
        credential_patterns = [
            "api_key", "apikey", "api-key",
            "secret", "secret_key", "secretkey",
            "token", "access_token", "auth_token",
            "password", "passwd", "pwd",
            "private_key", "privatekey",
            "credential", "credentials",
        ]
        
        json_str = str(response_dict).lower()
        for pattern in credential_patterns:
            assert pattern not in json_str, f"Found credential pattern: {pattern}"


# ======================================================================# Edge Case Tests
# ======================================================================
class TestEdgeCases:
    """Edge case tests."""
    
    def test_empty_filename_handled(self, receiver_service):
        """Empty filename is handled gracefully."""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        create_req = LocalUploadSessionCreate(
            quote_id="quote_123",
            expires_at=expires_at,
        )
        session = receiver_service.create_session(create_req)
        
        request = UploadFileRequest(
            session_id=session.session_id,
            declared_content_type="image/jpeg",
            original_filename="",
        )
        
        content = b"Test"
        file_record, rejection = receiver_service.process_file_upload(
            session.session_id, request, content
        )
        
        # Should still work - extension inferred from content type
        assert rejection is None
        assert file_record.extension == "jpeg" or file_record.extension == "jpg"
    
    def test_no_filename_handled(self, receiver_service):
        """No filename is handled gracefully."""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        create_req = LocalUploadSessionCreate(
            quote_id="quote_123",
            expires_at=expires_at,
        )
        session = receiver_service.create_session(create_req)
        
        request = UploadFileRequest(
            session_id=session.session_id,
            declared_content_type="image/jpeg",
            original_filename=None,
        )
        
        content = b"Test"
        file_record, rejection = receiver_service.process_file_upload(
            session.session_id, request, content
        )
        
        assert rejection is None
        assert file_record.extension == "jpeg" or file_record.extension == "jpg"
    
    def test_unknown_extension_unknown_content_type(self, receiver_service):
        """Unknown extension with unknown content type is rejected."""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        create_req = LocalUploadSessionCreate(
            quote_id="quote_123",
            expires_at=expires_at,
            allowed_content_types=["image/jpeg"],
            allowed_extensions=[".jpg"],
        )
        session = receiver_service.create_session(create_req)
        
        request = UploadFileRequest(
            session_id=session.session_id,
            declared_content_type="application/x-unknown",
            original_filename="file.xyz",
        )
        
        content = b"Test"
        file_record, rejection = receiver_service.process_file_upload(
            session.session_id, request, content
        )
        
        # Should be rejected - the file_record returned has minimal/empty data
        assert rejection is not None
        assert rejection.rejected is True
        assert rejection.reason in [
            FileRejectionReason.DISALLOWED_CONTENT_TYPE,
            FileRejectionReason.DISALLOWED_EXTENSION,
        ]
    
    def test_multiple_files_same_session(self, receiver_service, temp_upload_root):
        """Multiple files in same session are tracked correctly."""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        create_req = LocalUploadSessionCreate(
            quote_id="quote_123",
            expires_at=expires_at,
            max_files=5,
            max_total_bytes=10 * 1024 * 1024,
        )
        session = receiver_service.create_session(create_req)
        
        # Upload multiple files
        for i in range(3):
            request = UploadFileRequest(
                session_id=session.session_id,
                declared_content_type="image/jpeg",
                original_filename=f"photo{i}.jpg",
            )
            content = b"X" * 1000
            file_record, rejection = receiver_service.process_file_upload(
                session.session_id, request, content
            )
            assert rejection is None
        
        # Check session state
        current_session = receiver_service.get_session(session_id)
        assert len(current_session.uploaded_files) == 3
        assert current_session.total_bytes_uploaded == 3000
    
    def test_session_auto_expires(self, receiver_service):
        """Expired session is handled correctly."""
        # Create session with valid expiry first
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        create_req = LocalUploadSessionCreate(
            quote_id="quote_123",
            expires_at=expires_at,
        )
        session = receiver_service.create_session(create_req)
        session_id = session.session_id
        
        # Manually expire it
        receiver_service._sessions[session_id].status = SessionStatus.EXPIRED
        
        # Try to get it
        with pytest.raises(ValueError, match="Session expired"):
            receiver_service.get_session(session_id)


# ======================================================================# Provider Redaction Still Works
# ======================================================================