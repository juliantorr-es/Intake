"""Receiver models for Local Upload Receiver v0.

These models define the request/response structures for the local receiver API.
The Local Receiver is separate from the Local Console.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any, Optional
from pydantic import BaseModel, Field, ConfigDict
import secrets


# =============================================================================
# Enums
# =============================================================================

class ReceiverStatus(StrEnum):
    """Current status of the local receiver."""
    OFFLINE = "offline"
    ONLINE = "online"
    STARTING = "starting"
    SHUTTING_DOWN = "shutting_down"
    ERROR = "error"


class SessionStatus(StrEnum):
    """Status of an upload session."""
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class FileStatus(StrEnum):
    """Status of an uploaded file."""
    PENDING = "pending"
    UPLOADED = "uploaded"
    VALIDATED = "validated"
    REJECTED = "rejected"


# Allowed content types for v0
ALLOWED_CONTENT_TYPES = {
    # Images
    "image/jpeg": [".jpg", ".jpeg"],
    "image/png": [".png"],
    "image/webp": [".webp"],
    "image/heic": [".heic"],
    # Video
    "video/mp4": [".mp4"],
    "video/quicktime": [".mov"],
    # Documents
    "application/pdf": [".pdf"],
}

# Reverse mapping: extension -> canonical content type
ALLOWED_EXTENSIONS = {}
for content_type, exts in ALLOWED_CONTENT_TYPES.items():
    for ext in exts:
        ALLOWED_EXTENSIONS[ext.lower()] = content_type

# Flattened list of allowed extensions
ALLOWED_EXTENSIONS_LIST = list(ALLOWED_EXTENSIONS.keys())

# Default limits
DEFAULT_MAX_FILE_SIZE_BYTES = 150 * 1024 * 1024  # 150 MB
DEFAULT_MAX_FILES_PER_SESSION = 20
DEFAULT_MAX_TOTAL_BYTES_PER_SESSION = 500 * 1024 * 1024  # 500 MB
DEFAULT_SESSION_EXPIRY_MINUTES = 30


# =============================================================================
# Request/Response Models
# =============================================================================

class ReceiverHandshakeChallenge(BaseModel):
    """Challenge sent by route decision to verify receiver is available."""
    model_config = ConfigDict(json_schema_extra={
        "examples": [{
            "challenge_token": "abc123...",
            "expected_protocols": ["multipart"],
            "expected_capabilities": ["DIRECT_UPLOAD", "STREAMING_UPLOAD"],
        }]
    })
    
    challenge_token: str = Field(default_factory=lambda: secrets.token_hex(16))
    expected_protocols: list[str] = ["multipart"]
    expected_capabilities: list[str] = ["DIRECT_UPLOAD", "STREAMING_UPLOAD"]
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ReceiverHandshakeResponse(BaseModel):
    """Response from receiver handshake.
    
    No secrets are included. No filesystem paths are exposed.
    local_url is only included when local-dev mode is active.
    """
    model_config = ConfigDict(json_schema_extra={
        "examples": [{
            "receiver_id": "local_loopback_dev_001",
            "status": "online",
            "supported_protocols": ["multipart"],
            "max_file_size_bytes": 157286400,
            "max_files_per_session": 20,
            "supported_content_types": ["image/jpeg", "image/png", "application/pdf"],
            "expires_at": "2024-12-01T00:00:00Z",
            "local_url": "http://127.0.0.1:8001/receiver",
        }]
    })
    
    receiver_id: str
    status: ReceiverStatus
    supported_protocols: list[str] = ["multipart"]
    max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES
    max_files_per_session: int = DEFAULT_MAX_FILES_PER_SESSION
    max_total_bytes_per_session: int = DEFAULT_MAX_TOTAL_BYTES_PER_SESSION
    supported_content_types: list[str] = list(ALLOWED_CONTENT_TYPES.keys())
    supported_extensions: list[str] = ALLOWED_EXTENSIONS_LIST
    expires_at: datetime
    receiver_version: str = "0.1.0"
    # Only exposed in local-dev mode, never in production
    local_url: Optional[str] = None


class ReceiverRegistration(BaseModel):
    """Registration info for the receiver (internal use)."""
    receiver_id: str
    bind_address: str = "127.0.0.1"
    port: int = 8001
    is_loopback_only: bool = True
    registered_at: datetime = Field(default_factory=datetime.utcnow)


class ReceiverAvailabilityStatus(BaseModel):
    """Public-safe availability status of the receiver."""
    model_config = ConfigDict(json_schema_extra={
        "examples": [{
            "receiver_id": "local_loopback_dev_001",
            "status": "online",
            "bind_address_redacted": True,
            "loopback_only": True,
        }]
    })
    
    receiver_id: str
    status: ReceiverStatus
    bind_address_redacted: bool = True
    loopback_only: bool = True
    health_check_at: Optional[datetime] = None


# =============================================================================
# Upload Session Models
# =============================================================================

class LocalUploadSessionCreate(BaseModel):
    """Request to create a new upload session."""
    model_config = ConfigDict(json_schema_extra={
        "examples": [{
            "quote_id": "quote_abc123",
            "account_id": "account_xyz789",
            "expires_at": "2024-12-01T00:00:00Z",
            "allowed_content_types": ["image/jpeg", "image/png"],
            "allowed_extensions": [".jpg", ".jpeg", ".png"],
            "max_file_size_bytes": 157286400,
            "max_files": 20,
        }]
    })
    
    quote_id: str
    account_id: Optional[str] = None  # Can be redacted client reference
    expires_at: datetime
    allowed_content_types: list[str] = list(ALLOWED_CONTENT_TYPES.keys())
    allowed_extensions: list[str] = ALLOWED_EXTENSIONS_LIST
    max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES
    max_files: int = DEFAULT_MAX_FILES_PER_SESSION
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES_PER_SESSION
    # One-time token hash for session validation
    one_time_token_hash: Optional[str] = None


class LocalUploadSession(BaseModel):
    """An upload session on the local receiver."""
    model_config = ConfigDict(from_attributes=True)
    
    session_id: str
    quote_id: str
    account_id: Optional[str] = None
    status: SessionStatus = SessionStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime
    allowed_content_types: list[str] = list(ALLOWED_CONTENT_TYPES.keys())
    allowed_extensions: list[str] = ALLOWED_EXTENSIONS_LIST
    max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES
    max_files: int = DEFAULT_MAX_FILES_PER_SESSION
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES_PER_SESSION
    uploaded_files: list[str] = []  # List of file IDs
    total_bytes_uploaded: int = 0
    one_time_token_hash: Optional[str] = None


# =============================================================================
# File Upload Models
# =============================================================================

class LocalUploadedFileRecord(BaseModel):
    """Record of a file uploaded to the local receiver."""
    model_config = ConfigDict(from_attributes=True)
    
    file_id: str
    session_id: str
    quote_id: str
    original_filename_redacted: bool = True  # Original filename is NOT stored in path
    declared_content_type: str
    detected_content_type: Optional[str] = None
    extension: str
    size_bytes: int
    sha256: str
    status: FileStatus = FileStatus.PENDING
    stored_at: datetime = Field(default_factory=datetime.utcnow)
    storage_provider: str = "local_loopback_dev"
    # Internal storage reference (NOT exposed to client)
    storage_ref: str  # Server-side internal reference only


class UploadFileRequest(BaseModel):
    """Metadata for file upload (accompanies multipart file)."""
    session_id: str
    declared_content_type: str
    original_filename: Optional[str] = None  # Not used in storage path


# =============================================================================
# Receipt Models
# =============================================================================

class LocalUploadReceipt(BaseModel):
    """Receipt for a completed file upload.
    
    This is the public-safe form. No raw local paths are exposed.
    """
    model_config = ConfigDict(json_schema_extra={
        "examples": [{
            "upload_id": "upload_abc123",
            "session_id": "session_xyz789",
            "quote_id": "quote_123",
            "file_id": "file_def456",
            "size_bytes": 1024,
            "sha256": "abc123...",
            "declared_content_type": "image/jpeg",
            "extension": ".jpg",
            "stored_at": "2024-01-01T00:00:00Z",
            "storage_provider": "local_loopback_dev",
        }]
    })
    
    upload_id: str
    session_id: str
    quote_id: str
    file_id: str
    size_bytes: int
    sha256: str
    declared_content_type: str
    extension: str
    stored_at: datetime
    storage_provider: str = "local_loopback_dev"
    # Public-safe metadata only; no internal paths


class LocalUploadCompleteReceipt(BaseModel):
    """Receipt for a completed upload session."""
    model_config = ConfigDict(from_attributes=True)
    
    session_id: str
    quote_id: str
    total_files: int
    total_bytes: int
    completed_at: datetime = Field(default_factory=datetime.utcnow)
    file_receipts: list[LocalUploadReceipt] = []
    storage_provider: str = "local_loopback_dev"


class SessionCompleteRequest(BaseModel):
    """Request to mark a session as complete."""
    session_id: str
    quote_id: str


# =============================================================================
# Validation Error Models
# =============================================================================

class UploadValidationError(BaseModel):
    """Details about a file validation failure."""
    error_code: str
    error_message: str
    field: Optional[str] = None
    rejected_value: Optional[str] = None
    details: Optional[dict[str, Any]] = None


class FileRejectionReason(StrEnum):
    """Reasons a file might be rejected."""
    MISSING_FILE = "missing_file"
    EMPTY_FILE = "empty_file"
    OVER_SIZE_LIMIT = "over_size_limit"
    DISALLOWED_EXTENSION = "disallowed_extension"
    DISALLOWED_CONTENT_TYPE = "disallowed_content_type"
    EXTENSION_MISMATCH = "extension_mismatch"
    EXPIRED_SESSION = "expired_session"
    COMPLETED_SESSION = "completed_session"
    MAX_FILES_EXCEEDED = "max_files_exceeded"
    MAX_TOTAL_BYTES_EXCEEDED = "max_total_bytes_exceeded"
    INVALID_SESSION = "invalid_session"


class UploadRejectionResponse(BaseModel):
    """Response when a file upload is rejected."""
    rejected: bool = True
    reason: FileRejectionReason
    error_message: str
    session_id: Optional[str] = None
    file_id: Optional[str] = None
    details: Optional[dict[str, Any]] = None
