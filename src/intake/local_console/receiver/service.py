"""Local Receiver Service - business logic for upload receiver.

Handles:
- Session creation and validation
- File validation
- Upload processing
- Receiver state management
"""

import re
from datetime import datetime, timezone
from typing import Any, Optional

from intake.local_console.receiver.models import (
    ALLOWED_CONTENT_TYPES,
    ALLOWED_EXTENSIONS,
    DEFAULT_MAX_FILE_SIZE_BYTES,
    DEFAULT_MAX_FILES_PER_SESSION,
    DEFAULT_MAX_TOTAL_BYTES_PER_SESSION,
    DEFAULT_SESSION_EXPIRY_MINUTES,
    FileRejectionReason,
    FileStatus,
    LocalUploadSession,
    LocalUploadSessionCreate,
    LocalUploadedFileRecord,
    LocalUploadReceipt,
    LocalUploadCompleteReceipt,
    ReceiverHandshakeChallenge,
    ReceiverHandshakeResponse,
    ReceiverRegistration,
    ReceiverStatus,
    ReceiverAvailabilityStatus,
    SessionCompleteRequest,
    SessionStatus,
    UploadFileRequest,
    UploadRejectionResponse,
)
from intake.local_console.receiver.storage import LocalReceiverStorageService, get_storage_service


class LocalReceiverService:
    """Core business logic for the local upload receiver.
    
    This service manages:
    - Session lifecycle
    - File validation and storage
    - Receiver state
    """
    
    def __init__(self, storage_service: Optional[LocalReceiverStorageService] = None):
        self.storage = storage_service or get_storage_service()
        self.receiver_id = "local_loopback_dev_001"
        self.status = ReceiverStatus.ONLINE
        self._sessions: dict[str, LocalUploadSession] = {}
        self._files: dict[str, LocalUploadedFileRecord] = {}
        self._registration = ReceiverRegistration(
            receiver_id=self.receiver_id,
            bind_address="127.0.0.1",
            port=8001,
            is_loopback_only=True,
        )
    
    # =========================================================================
    # Receiver Lifecycle
    # =========================================================================
    
    def set_status(self, status: ReceiverStatus) -> None:
        """Update receiver status."""
        self.status = status
    
    def get_availability(self) -> ReceiverAvailabilityStatus:
        """Get current receiver availability status."""
        return ReceiverAvailabilityStatus(
            receiver_id=self.receiver_id,
            status=self.status,
            bind_address_redacted=True,
            loopback_only=True,
            health_check_at=datetime.now(timezone.utc),
        )
    
    # =========================================================================
    # Handshake
    # =========================================================================
    
    def perform_handshake(self, challenge: Optional[ReceiverHandshakeChallenge] = None) -> ReceiverHandshakeResponse:
        """Perform handshake with a potential client.
        
        Args:
            challenge: Optional challenge from route decision
            
        Returns:
            Handshake response with receiver capabilities
        """
        expires_at = datetime.now(timezone.utc)
        
        return ReceiverHandshakeResponse(
            receiver_id=self.receiver_id,
            status=self.status,
            supported_protocols=["multipart"],
            max_file_size_bytes=DEFAULT_MAX_FILE_SIZE_BYTES,
            max_files_per_session=DEFAULT_MAX_FILES_PER_SESSION,
            max_total_bytes_per_session=DEFAULT_MAX_TOTAL_BYTES_PER_SESSION,
            supported_content_types=list(ALLOWED_CONTENT_TYPES.keys()),
            supported_extensions=list(ALLOWED_EXTENSIONS.keys()),
            expires_at=expires_at,
            receiver_version="0.1.0",
            local_url="http://127.0.0.1:8001/receiver",  # Only in local-dev
        )
    
    # =========================================================================
    # Session Management
    # =========================================================================
    
    def create_session(self, request: LocalUploadSessionCreate) -> LocalUploadSession:
        """Create a new upload session.
        
        Args:
            request: Session creation request
            
        Returns:
            Created session
            
        Raises:
            ValueError: If session data is invalid
        """
        self._validate_session_request(request)
        
        session_id = self.storage.generate_file_id()
        
        # Use provided expiry or default
        expires_at = request.expires_at if request.expires_at > datetime.now(timezone.utc) else \
            datetime.now(timezone.utc) + timezone.timedelta(minutes=DEFAULT_SESSION_EXPIRY_MINUTES)
        
        session = LocalUploadSession(
            session_id=session_id,
            quote_id=request.quote_id,
            account_id=request.account_id,
            status=SessionStatus.ACTIVE,
            created_at=datetime.now(timezone.utc),
            expires_at=expires_at,
            allowed_content_types=request.allowed_content_types,
            allowed_extensions=request.allowed_extensions,
            max_file_size_bytes=request.max_file_size_bytes,
            max_files=request.max_files,
            max_total_bytes=request.max_total_bytes,
            one_time_token_hash=request.one_time_token_hash,
        )
        
        self._sessions[session_id] = session
        self.storage.create_session_directory(session_id)
        
        return session
    
    def _validate_session_request(self, request: LocalUploadSessionCreate) -> None:
        """Validate session creation request.
        
        Raises:
            ValueError: If validation fails
        """
        if not request.quote_id:
            raise ValueError("quote_id is required")
        
        if request.expires_at < datetime.now(timezone.utc):
            raise ValueError("expires_at must be in the future")
        
        if request.max_file_size_bytes <= 0:
            raise ValueError("max_file_size_bytes must be positive")
        
        if request.max_files <= 0:
            raise ValueError("max_files must be positive")
        
        if request.max_total_bytes <= 0:
            raise ValueError("max_total_bytes must be positive")
        
        # Validate content types
        for ct in request.allowed_content_types:
            if ct not in ALLOWED_CONTENT_TYPES:
                raise ValueError(f"Content type not allowed: {ct}")
        
        # Validate extensions
        for ext in request.allowed_extensions:
            if ext.lower() not in ALLOWED_EXTENSIONS:
                raise ValueError(f"Extension not allowed: {ext}")
    
    def get_session(self, session_id: str) -> LocalUploadSession:
        """Get an existing session.
        
        Args:
            session_id: The session ID
            
        Returns:
            The session
            
        Raises:
            ValueError: If session not found or expired
        """
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")
        
        # Check expiry
        if session.expires_at < datetime.now(timezone.utc):
            session.status = SessionStatus.EXPIRED
            raise ValueError(f"Session expired: {session_id}")
        
        return session
    
    def complete_session(self, request: SessionCompleteRequest) -> LocalUploadCompleteReceipt:
        """Mark a session as complete.
        
        Args:
            request: Session completion request
            
        Returns:
            Completion receipt
            
        Raises:
            ValueError: If session not found, expired, or already completed
        """
        session = self.get_session(request.session_id)
        
        if session.status == SessionStatus.COMPLETED:
            raise ValueError(f"Session already completed: {request.session_id}")
        
        if session.quote_id != request.quote_id:
            raise ValueError(f"Quote ID mismatch for session: {request.session_id}")
        
        # Mark as completed
        session.status = SessionStatus.COMPLETED
        
        # Gather file receipts (public-safe form)
        file_receipts = []
        for file_id in session.uploaded_files:
            file_record = self._files.get(file_id)
            if file_record and file_record.session_id == request.session_id:
                receipt = LocalUploadReceipt(
                    upload_id=self.storage.generate_upload_id(),
                    session_id=session.session_id,
                    quote_id=session.quote_id,
                    file_id=file_record.file_id,
                    size_bytes=file_record.size_bytes,
                    sha256=file_record.sha256,
                    declared_content_type=file_record.declared_content_type,
                    extension=file_record.extension,
                    stored_at=file_record.stored_at,
                    storage_provider="local_loopback_dev",
                )
                file_receipts.append(receipt)
        
        return LocalUploadCompleteReceipt(
            session_id=session.session_id,
            quote_id=session.quote_id,
            total_files=len(file_receipts),
            total_bytes=sum(f.size_bytes for f in file_receipts),
            completed_at=datetime.now(timezone.utc),
            file_receipts=file_receipts,
            storage_provider="local_loopback_dev",
        )
    
    # =========================================================================
    # File Upload
    # =========================================================================
    
    def validate_file_upload(
        self,
        session_id: str,
        request: UploadFileRequest,
        file_size: int,
    ) -> tuple[Optional[str], Optional[FileRejectionReason]]:
        """Validate a file upload request against session rules.
        
        Args:
            session_id: The session ID
            request: The upload request
            file_size: Size of the file in bytes
            
        Returns:
            Tuple of (extension or None, rejection reason or None)
            If extension is returned, it's been validated.
            If rejection reason is returned, upload should be rejected.
        """
        try:
            session = self.get_session(session_id)
        except ValueError:
            return None, FileRejectionReason.INVALID_SESSION
        
        # Check session status
        if session.status == SessionStatus.COMPLETED:
            return None, FileRejectionReason.COMPLETED_SESSION
        
        if session.status == SessionStatus.EXPIRED:
            return None, FileRejectionReason.EXPIRED_SESSION
        
        # Check file size
        if file_size <= 0:
            return None, FileRejectionReason.EMPTY_FILE
        
        if file_size > session.max_file_size_bytes:
            return None, FileRejectionReason.OVER_SIZE_LIMIT
        
        # Check total bytes
        if session.total_bytes_uploaded + file_size > session.max_total_bytes:
            return None, FileRejectionReason.MAX_TOTAL_BYTES_EXCEEDED
        
        # Check file count
        if len(session.uploaded_files) >= session.max_files:
            return None, FileRejectionReason.MAX_FILES_EXCEEDED
        
        # Validate content type
        declared_ct = request.declared_content_type
        if declared_ct not in session.allowed_content_types and declared_ct not in ALLOWED_CONTENT_TYPES:
            return None, FileRejectionReason.DISALLOWED_CONTENT_TYPE
        
        # Extract and validate extension from original filename if provided
        extension = None
        if request.original_filename:
            # Extract extension from filename
            import os as os_module
            _, ext = os_module.path.splitext(request.original_filename)
            ext = ext.lower()
            
            if ext:
                # Keep the dot for consistency with our allowlists
                # ALLOWED_EXTENSIONS has keys like ".jpg", ".png"
                if not ext.startswith("."):
                    ext = f".{ext}"
                
                # Validate against session rules
                # Normalize session extensions to also have dots
                normalized_session_extensions = set(
                    e if e.startswith(".") else f".{e}" for e in session.allowed_extensions
                )
                
                if ext not in normalized_session_extensions and ext not in ALLOWED_EXTENSIONS:
                    return None, FileRejectionReason.DISALLOWED_EXTENSION
                
                # Check extension matches content type
                if ext in ALLOWED_EXTENSIONS:
                    expected_ct = ALLOWED_EXTENSIONS[ext]
                    if declared_ct != expected_ct:
                        return None, FileRejectionReason.EXTENSION_MISMATCH
                
                # Store without dot for the file record
                extension = ext.lstrip(".")
            else:
                # No extension in filename - might still be valid if content type only
                pass
        
        # If we couldn't determine extension from filename, try from content type
        if not extension and declared_ct in ALLOWED_CONTENT_TYPES:
            # Use canonical extension for this content type
            # Pick the first from the allowlist
            ext = ALLOWED_CONTENT_TYPES[declared_ct][0]
            extension = ext.lstrip(".")
        
        return extension, None
    
    def process_file_upload(
        self,
        session_id: str,
        request: UploadFileRequest,
        file_content: bytes,
    ) -> tuple[LocalUploadedFileRecord, Optional[UploadRejectionResponse]]:
        """Process a file upload and store it.
        
        Args:
            session_id: The session ID
            request: The upload request
            file_content: The raw file bytes
            
        Returns:
            Tuple of (file_record, rejection_response)
            If rejection_response is not None, upload was rejected.
        """
        # Validate first
        file_size = len(file_content)
        extension, rejection = self.validate_file_upload(
            session_id, request, file_size
        )
        
        if rejection:
            return None, UploadRejectionResponse(
                rejected=True,
                reason=rejection,
                error_message=f"File rejected: {rejection.value}",
                session_id=session_id,
                details={"file_size": file_size},
            )
        
        # Get session (already validated)
        session = self._sessions[session_id]
        
        # Generate IDs
        file_id = self.storage.generate_file_id()
        upload_id = self.storage.generate_upload_id()
        
        # Compute SHA256
        import hashlib
        sha256 = hashlib.sha256(file_content).hexdigest()
        
        # Store file
        try:
            final_path, _ = self.storage.store_file(
                session_id=session_id,
                file_id=file_id,
                extension=extension,
                file_content=file_content,
                declared_content_type=request.declared_content_type,
            )
        except ValueError as e:
            return LocalUploadedFileRecord(file_id=""), UploadRejectionResponse(
                rejected=True,
                reason=FileRejectionReason.INVALID_SESSION,
                error_message=str(e),
                session_id=session_id,
            )
        
        # Create internal storage reference (not exposed to client)
        storage_ref = self.storage.get_storage_ref(session_id, file_id, extension)
        
        # Create file record
        file_record = LocalUploadedFileRecord(
            file_id=file_id,
            session_id=session_id,
            quote_id=session.quote_id,
            original_filename_redacted=True,
            declared_content_type=request.declared_content_type,
            detected_content_type=None,  # Would be populated by actual detection
            extension=extension if extension else "",
            size_bytes=file_size,
            sha256=sha256,
            status=FileStatus.UPLOADED,
            stored_at=datetime.now(timezone.utc),
            storage_provider="local_loopback_dev",
            storage_ref=storage_ref,
        )
        
        # Update session
        session.uploaded_files.append(file_id)
        session.total_bytes_uploaded += file_size
        
        # Store file record
        self._files[file_id] = file_record
        
        # Return with no rejection
        return file_record, None
    
    def process_streamed_file_upload(
        self,
        session_id: str,
        request: UploadFileRequest,
        file_obj: Any,  # UploadFile or similar
    ) -> tuple[LocalUploadedFileRecord, Optional[UploadRejectionResponse]]:
        """Process a streamed file upload.
        
        Args:
            session_id: The session ID
            request: The upload request
            file_obj: File-like object (UploadFile)
            
        Returns:
            Tuple of (file_record, rejection_response)
        """
        import hashlib
        
        # Validate first - we need to know size upfront or stream to find it
        # For streaming, we'll read to find size but there's a tradeoff
        # For now, assume file_obj has a size attribute or seekable
        
        try:
            # Try to get size
            if hasattr(file_obj, "size") and callable(file_obj.size):
                file_size = file_obj.size()
            elif hasattr(file_obj, "size"):
                file_size = file_obj.size
            else:
                # Need to read to find size - not ideal for streaming
                # For now, use a fallback
                file_size = 0
        except Exception:
            file_size = 0
        
        # This is a limitation of v0 - we can't validate size before reading
        # For the tests with small files, this is acceptable
        
        # For now, do validation with size=0 (will be caught by empty check)
        extension, rejection = self.validate_file_upload(
            session_id, request, file_size or 1  # Assume non-empty for now
        )
        
        if rejection and rejection != FileRejectionReason.EMPTY_FILE:
            return None, UploadRejectionResponse(
                rejected=True,
                reason=rejection,
                error_message=f"File rejected: {rejection.value}",
                session_id=session_id,
            )
        
        # Get session
        session = self._sessions[session_id]
        
        # Generate IDs
        file_id = self.storage.generate_file_id()
        upload_id = self.storage.generate_upload_id()
        
        # Store with streaming
        try:
            final_path, sha256, actual_size = self.storage.stream_store_file(
                session_id=session_id,
                file_id=file_id,
                extension=extension,
                file_obj=file_obj,
            )
        except ValueError as e:
            return None, UploadRejectionResponse(
                rejected=True,
                reason=FileRejectionReason.INVALID_SESSION,
                error_message=str(e),
                session_id=session_id,
            )
        
        # Re-validate with actual size
        if actual_size == 0:
            return None, UploadRejectionResponse(
                rejected=True,
                reason=FileRejectionReason.EMPTY_FILE,
                error_message="File is empty",
                session_id=session_id,
            )
        
        if actual_size > session.max_file_size_bytes:
            # Clean up the file we just stored
            self.storage.delete_file(session_id, file_id, extension)
            return None, UploadRejectionResponse(
                rejected=True,
                reason=FileRejectionReason.OVER_SIZE_LIMIT,
                error_message=f"File too large: {actual_size} > {session.max_file_size_bytes}",
                session_id=session_id,
            )
        
        # Check total bytes
        if session.total_bytes_uploaded + actual_size > session.max_total_bytes:
            self.storage.delete_file(session_id, file_id, extension)
            return None, UploadRejectionResponse(
                rejected=True,
                reason=FileRejectionReason.MAX_TOTAL_BYTES_EXCEEDED,
                error_message="Session total bytes exceeded",
                session_id=session_id,
            )
        
        # Re-check file count (might have changed during upload)
        if len(session.uploaded_files) >= session.max_files:
            self.storage.delete_file(session_id, file_id, extension)
            return None, UploadRejectionResponse(
                rejected=True,
                reason=FileRejectionReason.MAX_FILES_EXCEEDED,
                error_message="Maximum files exceeded",
                session_id=session_id,
            )
        
        # Create storage reference
        storage_ref = self.storage.get_storage_ref(session_id, file_id, extension)
        
        # Create file record
        file_record = LocalUploadedFileRecord(
            file_id=file_id,
            session_id=session_id,
            quote_id=session.quote_id,
            original_filename_redacted=True,
            declared_content_type=request.declared_content_type,
            detected_content_type=None,
            extension=extension if extension else "",
            size_bytes=actual_size,
            sha256=sha256,
            status=FileStatus.UPLOADED,
            stored_at=datetime.now(timezone.utc),
            storage_provider="local_loopback_dev",
            storage_ref=storage_ref,
        )
        
        # Update session
        session.uploaded_files.append(file_id)
        session.total_bytes_uploaded += actual_size
        
        # Store file record
        self._files[file_id] = file_record
        
        return file_record, None
    
    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    def get_file_record(self, file_id: str) -> Optional[LocalUploadedFileRecord]:
        """Get a file record by ID."""
        return self._files.get(file_id)
    
    def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions and their files.
        
        Returns:
            Number of sessions cleaned up
        """
        now = datetime.now(timezone.utc)
        cleaned = 0
        
        expired_sessions = [
            sid for sid, s in self._sessions.items()
            if s.expires_at < now or s.status == SessionStatus.EXPIRED
        ]
        
        for sid in expired_sessions:
            session = self._sessions[sid]
            if session.status != SessionStatus.COMPLETED:
                session.status = SessionStatus.EXPIRED
            
            # Clean up files
            for file_id in session.uploaded_files:
                file_record = self._files.get(file_id)
                if file_record:
                    self.storage.delete_file(sid, file_id, file_record.extension)
                    del self._files[file_id]
            
            # Clean up directory
            self.storage.cleanup_session(sid)
            del self._sessions[sid]
            cleaned += 1
        
        return cleaned
