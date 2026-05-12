"""Storage service for local-dev binary uploads."""

import os
import secrets
import shutil
from pathlib import Path
from typing import Any

from intake.config import get_settings


class StorageService:
    """Service for local-dev binary upload storage.
    
    This service manages storing uploaded files on the local filesystem.
    Files are stored in .build/intake/uploads/ with random unguessable names.
    """

    def __init__(self, upload_root: Path | None = None):
        """Initialize storage service.
        
        Args:
            upload_root: Root directory for uploads (defaults to .build/intake/uploads/)
        """
        if upload_root:
            self._upload_root = upload_root
        else:
            settings = get_settings()
            # Default to .build/intake/uploads/
            self._upload_root = Path(".build/intake/uploads").absolute()
        
        # Ensure upload root exists
        self._upload_root.mkdir(parents=True, exist_ok=True)

    def store_file(self, quote_id: str, file_content: bytes, extension: str) -> tuple[str, str]:
        """Store a file in local storage.
        
        Args:
            quote_id: ID of the quote the file belongs to
            file_content: Binary content of the file
            extension: File extension (e.g., ".jpg")
            
        Returns:
            Tuple of (storage_object_id, storage_relative_path)
        """
        # Generate a random unguessable storage object ID
        storage_object_id = secrets.token_hex(16)
        
        # Partition by quote_id
        quote_dir = self._upload_root / f"quote_{quote_id}"
        quote_dir.mkdir(parents=True, exist_ok=True)
        
        # Final filename
        filename = f"{storage_object_id}{extension}"
        file_path = quote_dir / filename
        
        # Check path safety (prevent path traversal)
        if not str(file_path.absolute()).startswith(str(self._upload_root.absolute())):
            raise ValueError("Invalid storage path")
        
        # Write bytes
        with open(file_path, "wb") as f:
            f.write(file_content)
            
        # Return relative path for storage in DB
        relative_path = str(file_path.relative_to(self._upload_root))
        
        return storage_object_id, relative_path

    def get_file_path(self, relative_path: str) -> Path:
        """Get the absolute path to a stored file.
        
        Args:
            relative_path: Relative path from upload root
            
        Returns:
            Absolute Path to the file
            
        Raises:
            ValueError: If path is invalid or outside upload root
        """
        full_path = (self._upload_root / relative_path).absolute()
        
        # Check path safety
        if not str(full_path).startswith(str(self._upload_root.absolute())):
            raise ValueError("Invalid storage path")
            
        return full_path

    def delete_file(self, relative_path: str) -> bool:
        """Soft-delete/remove a file from disk.
        
        For this slice, we just delete the file.
        
        Args:
            relative_path: Relative path from upload root
            
        Returns:
            True if deleted, False if not found
        """
        try:
            path = self.get_file_path(relative_path)
            if path.exists():
                path.unlink()
                return True
        except (ValueError, OSError):
            pass
        return False


def get_storage_service() -> StorageService:
    """Get a storage service instance."""
    return StorageService()
