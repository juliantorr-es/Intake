"""Validation service for binary uploads."""

import mimetypes
from pathlib import Path
from typing import Any

from intake.domain.quotes import QuoteStatus


class UploadValidationService:
    """Service for validating binary uploads.
    
    Handles size limits, file extension allowlists, and MIME type validation.
    """

    # Allowed extensions and MIME types
    ALLOWED_POLICIES = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".heic": "image/heic",
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".pdf": "application/pdf",
    }

    # Size limits in bytes
    LIMITS = {
        "IMAGE": 15 * 1024 * 1024,      # 15 MB
        "PDF": 20 * 1024 * 1024,        # 20 MB
        "VIDEO": 150 * 1024 * 1024,     # 150 MB
        "GLOBAL_MAX": 150 * 1024 * 1024, # 150 MB for this slice (video limit)
        "MAX_FILES_PER_QUOTE": 20,
        "MAX_TOTAL_BYTES_PER_QUOTE": 500 * 1024 * 1024, # 500 MB
    }

    # Mutable quote statuses for uploads
    ALLOWED_QUOTE_STATUSES = {
        QuoteStatus.DRAFT,
        QuoteStatus.SUBMITTED,
        QuoteStatus.NEEDS_REVIEW,
        QuoteStatus.REVIEWING,
    }

    def validate_file(self, filename: str, content_type: str, size_bytes: int) -> str:
        """Validate a file's metadata before storage.
        
        Args:
            filename: Original filename from browser
            content_type: Declared Content-Type from browser
            size_bytes: Actual size of uploaded bytes
            
        Returns:
            The normalized extension (including dot, e.g., ".jpg")
            
        Raises:
            ValueError: If validation fails
        """
        if not filename:
            raise ValueError("Missing filename")
        
        if size_bytes <= 0:
            raise ValueError("File is empty")

        # Check global max size
        if size_bytes > self.LIMITS["GLOBAL_MAX"]:
            raise ValueError(f"File exceeds maximum size of {self.LIMITS['GLOBAL_MAX'] // (1024*1024)}MB")

        # Get extension
        ext = Path(filename).suffix.lower()
        if not ext:
            raise ValueError("File has no extension")
        
        if ext not in self.ALLOWED_POLICIES:
            raise ValueError(f"Disallowed file extension: {ext}")

        # Check specific limits
        if ext == ".pdf" and size_bytes > self.LIMITS["PDF"]:
            raise ValueError(f"PDF exceeds maximum size of {self.LIMITS['PDF'] // (1024*1024)}MB")
        elif ext in (".mp4", ".mov") and size_bytes > self.LIMITS["VIDEO"]:
            raise ValueError(f"Video exceeds maximum size of {self.LIMITS['VIDEO'] // (1024*1024)}MB")
        elif ext in (".jpg", ".jpeg", ".png", ".webp", ".heic") and size_bytes > self.LIMITS["IMAGE"]:
            raise ValueError(f"Image exceeds maximum size of {self.LIMITS['IMAGE'] // (1024*1024)}MB")

        # Basic MIME type check (not authoritative but good for consistency)
        # We allow a small mismatch if the extension is explicitly in our list,
        # but we log/check if they are completely different.
        expected_mime = self.ALLOWED_POLICIES.get(ext)
        if content_type and expected_mime and content_type != expected_mime:
            # Some browsers might send slightly different mimes, but if they are 
            # wildly different (e.g., .jpg declared as application/exe), we reject.
            if content_type.split('/')[0] != expected_mime.split('/')[0] and ext != ".pdf":
                raise ValueError(f"MIME type mismatch: declared {content_type} for {ext}")

        return ext

    def can_upload_to_quote(self, quote_status: QuoteStatus, current_upload_count: int, current_total_bytes: int) -> bool:
        """Check if more files can be uploaded to a quote.
        
        Args:
            quote_status: Current status of the quote
            current_upload_count: Number of existing uploads
            current_total_bytes: Total bytes already uploaded
            
        Returns:
            True if allowed
            
        Raises:
            ValueError: If not allowed with specific reason
        """
        if quote_status not in self.ALLOWED_QUOTE_STATUSES:
            raise ValueError(f"Quote status '{quote_status}' does not allow uploads")
        
        if current_upload_count >= self.LIMITS["MAX_FILES_PER_QUOTE"]:
            raise ValueError(f"Quote already has maximum number of files ({self.LIMITS['MAX_FILES_PER_QUOTE']})")
        
        if current_total_bytes >= self.LIMITS["MAX_TOTAL_BYTES_PER_QUOTE"]:
            raise ValueError("Quote has reached total upload size limit")
            
        return True


def get_upload_validation_service() -> UploadValidationService:
    """Get a validation service instance."""
    return UploadValidationService()
