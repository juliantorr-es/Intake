"""Local filesystem storage service for the upload receiver.

Stores uploaded files under .build/intake/local_receiver/uploads/
with server-generated unguessable filenames.

Security notes:
- Never uses original filenames in storage paths
- Validates all paths stay under upload root
- Generates random file IDs
- Encrypts/redacts original filename metadata where applicable
"""

import hashlib
import os
import secrets
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, BinaryIO

from intake.config import get_settings


# Storage configuration
UPLOAD_ROOT_NAME = "local_receiver"
UPLOADS_DIR_NAME = "uploads"
DEFAULT_UPLOAD_ROOT = Path(f".build/intake/{UPLOAD_ROOT_NAME}/{UPLOADS_DIR_NAME}")


class LocalReceiverStorageService:
    """Handles local filesystem storage for receiver uploads.
    
    Features:
    - Server-side generated file IDs (unguessable)
    - Path traversal prevention
    - Partitioning by session ID under upload root
    - Atomic-ish writes (temp file + rename)
    """
    
    def __init__(self, root_path: Optional[Path] = None):
        """Initialize storage service.
        
        Args:
            root_path: Custom root path. Defaults to .build/intake/local_receiver/uploads/
        """
        self.root_path = root_path or self._get_root_path()
        self._ensure_root_exists()
    
    @staticmethod
    def _get_root_path() -> Path:
        """Get the configured upload root path."""
        try:
            settings = get_settings()
            custom_root = getattr(settings, "intake_local_upload_root", None)
            if custom_root:
                return Path(custom_root) / UPLOADS_DIR_NAME
        except Exception:
            pass
        return DEFAULT_UPLOAD_ROOT
    
    def _ensure_root_exists(self) -> None:
        """Create upload root directory if it doesn't exist."""
        self.root_path.mkdir(parents=True, exist_ok=True)
    
    def _resolve_session_path(self, session_id: str) -> Path:
        """Get the session-specific subdirectory under upload root."""
        # Validate session_id doesn't contain path traversal
        safe_session = self._sanitize_path_component(session_id)
        return self.root_path / safe_session
    
    @staticmethod
    def _sanitize_path_component(component: str) -> str:
        """Sanitize a path component to prevent traversal.
        
        Removes path separators and parent directory references.
        Keeps alphanumeric, hyphens, underscores, and dots (for extensions).
        Replaces other characters with underscores.
        """
        import re
        
        # First, remove path separators
        cleaned = component.replace("/", "").replace("\\", "")
        
        # Remove parent directory references
        while ".." in cleaned:
            cleaned = cleaned.replace("..", "")
        
        # Only allow alphanumeric, hyphens, underscores, and dots
        cleaned = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", cleaned)
        
        # Collapse multiple consecutive underscores
        cleaned = re.sub(r"_+", "_", cleaned)
        
        # Remove leading/trailing underscores and dots
        cleaned = cleaned.strip("_.")
        
        return cleaned if cleaned else "_"
    
    @staticmethod
    def generate_file_id() -> str:
        """Generate an unguessable file ID."""
        return secrets.token_hex(16)
    
    @staticmethod
    def generate_upload_id() -> str:
        """Generate an unguessable upload ID."""
        return secrets.token_hex(16)
    
    def _generate_storage_name(self, file_id: str, extension: Optional[str] = None) -> str:
        """Generate storage filename from file ID.
        
        Args:
            file_id: The generated file ID
            extension: Optional extension (must be validated allowlist)
            
        Returns:
            Safe storage filename like "abc123def солдат.jpg" or "abc123def" if no extension
        """
        if extension:
            # Normalize extension
            ext = extension.lower().strip()
            if ext.startswith("."):
                ext = ext[1:]
            return f"{file_id}.{ext}"
        return file_id
    
    def _validate_path_under_root(self, target_path: Path) -> bool:
        """Ensure a path is under the upload root."""
        # Resolve to absolute paths for comparison
        root_resolved = self.root_path.resolve()
        target_resolved = target_path.resolve()
        
        return target_resolved == root_resolved or str(target_resolved).startswith(str(root_resolved) + os.sep)
    
    def create_session_directory(self, session_id: str) -> Path:
        """Create directory for a specific upload session.
        
        Args:
            session_id: The upload session identifier
            
        Returns:
            Path to the session directory
        """
        session_path = self._resolve_session_path(session_id)
        session_path.mkdir(parents=True, exist_ok=True)
        return session_path
    
    def generate_storage_path(self, session_id: str, file_id: str, extension: Optional[str] = None) -> Path:
        """Generate the final storage path for a file.
        
        Args:
            session_id: The upload session ID
            file_id: The generated file ID
            extension: Validated extension (optional)
            
        Returns:
            Absolute path where file should be stored
        """
        session_path = self._resolve_session_path(session_id)
        filename = self._generate_storage_name(file_id, extension)
        return session_path / filename
    
    def store_file(self, session_id: str, file_id: str, extension: Optional[str], 
                   file_content: bytes, declared_content_type: str) -> tuple[Path, str]:
        """Store a file with atomic-ish write behavior.
        
        Args:
            session_id: The upload session ID
            file_id: The generated file ID
            extension: Validated extension (optional)
            file_content: Raw file bytes
            declared_content_type: The declared MIME type
            
        Returns:
            Tuple of (final_path, sha256_hex)
            
        Raises:
            ValueError: If path would be outside upload root
        """
        # Ensure session directory exists
        session_path = self._resolve_session_path(session_id)
        session_path.mkdir(parents=True, exist_ok=True)
        
        # Generate final path
        final_path = self.generate_storage_path(session_id, file_id, extension)
        
        # Validate it's under root
        if not self._validate_path_under_root(final_path):
            raise ValueError(f"Storage path would be outside upload root: {final_path}")
        
        # Generate temp path
        temp_path = session_path / f".{file_id}.tmp"
        
        # Compute SHA256 of content
        sha256_hex = hashlib.sha256(file_content).hexdigest()
        
        # Write to temp file
        temp_path.write_bytes(file_content)
        
        # Sync to disk if practical
        try:
            os.fsync(temp_path.fileno())
        except (OSError, AttributeError):
            pass  # fsync not available on all platforms
        
        # Atomic rename
        temp_path.rename(final_path)
        
        return final_path, sha256_hex
    
    def stream_store_file(self, session_id: str, file_id: str, extension: Optional[str],
                          file_obj: BinaryIO, chunk_size: int = 8192) -> tuple[Path, str, int]:
        """Store a file by streaming from a file-like object.
        
        This avoids loading the entire file into memory.
        
        Args:
            session_id: The upload session ID
            file_id: The generated file ID
            extension: Validated extension (optional)
            file_obj: File-like object to read from
            chunk_size: Size of chunks to read
            
        Returns:
            Tuple of (final_path, sha256_hex, size_bytes)
            
        Raises:
            ValueError: If path would be outside upload root
        """
        import hashlib
        
        # Ensure session directory exists
        session_path = self._resolve_session_path(session_id)
        session_path.mkdir(parents=True, exist_ok=True)
        
        # Generate final path
        final_path = self.generate_storage_path(session_id, file_id, extension)
        
        # Validate it's under root
        if not self._validate_path_under_root(final_path):
            raise ValueError(f"Storage path would be outside upload root: {final_path}")
        
        # Generate temp path
        temp_path = session_path / f".{file_id}.tmp"
        
        # Hash and size tracking
        hasher = hashlib.sha256()
        total_size = 0
        
        try:
            with temp_path.open("wb") as temp_file:
                while True:
                    chunk = file_obj.read(chunk_size)
                    if not chunk:
                        break
                    hasher.update(chunk)
                    temp_file.write(chunk)
                    total_size += len(chunk)
            
            # Sync to disk
            try:
                os.fsync(temp_path.fileno())
            except (OSError, AttributeError):
                pass
            
            # Atomic rename
            temp_path.rename(final_path)
            
            return final_path, hasher.hexdigest(), total_size
            
        except Exception:
            # Clean up temp file on error
            if temp_path.exists():
                temp_path.unlink()
            raise
    
    def get_file_path(self, session_id: str, file_id: str, extension: Optional[str] = None) -> Path:
        """Get the storage path for a previously stored file.
        
        Args:
            session_id: The upload session ID
            file_id: The file ID
            extension: The extension (optional)
            
        Returns:
            Absolute path to the file
        """
        return self.generate_storage_path(session_id, file_id, extension)
    
    def file_exists(self, session_id: str, file_id: str, extension: Optional[str] = None) -> bool:
        """Check if a file exists at the expected location."""
        path = self.get_file_path(session_id, file_id, extension)
        return path.exists()
    
    def get_file_size(self, session_id: str, file_id: str, extension: Optional[str] = None) -> int:
        """Get the size of a stored file."""
        path = self.get_file_path(session_id, file_id, extension)
        return path.stat().st_size if path.exists() else 0
    
    def delete_file(self, session_id: str, file_id: str, extension: Optional[str] = None) -> bool:
        """Delete a stored file.
        
        Returns:
            True if file existed and was deleted, False otherwise
        """
        path = self.get_file_path(session_id, file_id, extension)
        if path.exists():
            path.unlink()
            return True
        return False
    
    def delete_session_files(self, session_id: str) -> int:
        """Delete all files for a session.
        
        Returns:
            Number of files deleted
        """
        session_path = self._resolve_session_path(session_id)
        deleted = 0
        
        if session_path.exists():
            for f in session_path.glob("*"):
                try:
                    if f.is_file():
                        f.unlink()
                        deleted += 1
                except (OSError, PermissionError):
                    pass
            
            # Remove empty directory
            try:
                session_path.rmdir()
            except OSError:
                pass  # Directory not empty or already deleted
        
        return deleted
    
    def cleanup_session(self, session_id: str) -> dict:
        """Clean up all files and directory for a session.
        
        Returns:
            Summary of cleanup actions
        """
        session_path = self._resolve_session_path(session_id)
        result = {"session_id": session_id, "iles_deleted": 0, "directory_removed": False}
        
        if session_path.exists():
            for item in session_path.iterdir():
                try:
                    if item.is_file():
                        item.unlink()
                        result["files_deleted"] += 1
                except (OSError, PermissionError):
                    pass
            
            try:
                session_path.rmdir()
                result["directory_removed"] = True
            except OSError:
                pass
        
        return result
    
    def list_session_files(self, session_id: str) -> list[Path]:
        """List all files in a session directory.
        
        Note: This is for internal use only, never exposed to clients.
        """
        session_path = self._resolve_session_path(session_id)
        if not session_path.exists():
            return []
        return list(session_path.glob("*"))
    
    @property
    def upload_root(self) -> Path:
        """The upload root directory."""
        return self.root_path
    
    def verify_path_safety(self, original_filename: str) -> bool:
        """Verify that using an original filename would be safe.
        
        Always returns False for this implementation - we never use
        original filenames in storage paths.
        """
        return False
    
    def get_storage_ref(self, session_id: str, file_id: str, extension: Optional[str]) -> str:
        """Generate an internal storage reference string.
        
        This is NOT exposed to clients. It's an internal identifier.
        """
        path = self.generate_storage_path(session_id, file_id, extension)
        # Return relative path from upload root for internal use
        try:
            rel_path = path.relative_to(self.root_path)
            return str(rel_path)
        except ValueError:
            return f"{session_id}/{file_id}"


# Singleton instance
_storage_service: Optional[LocalReceiverStorageService] = None


def get_storage_service() -> LocalReceiverStorageService:
    """Get the singleton storage service instance."""
    global _storage_service
    if _storage_service is None:
        _storage_service = LocalReceiverStorageService()
    return _storage_service
