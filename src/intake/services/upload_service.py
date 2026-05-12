"""Service for coordinating binary uploads."""

import json
from typing import Any

from fastapi import HTTPException, UploadFile

from intake.domain.events import Event, EventActorType, EventType
from intake.domain.quotes import Quote, Upload, UploadStatus
from intake.services.crypto_service import get_crypto_service
from intake.services.storage_service import get_storage_service
from intake.services.upload_validation_service import get_upload_validation_service
from intake.storage.repositories import (
    AccountRepository,
    EventRepository,
    PasskeyRepository,
    QuoteRepository,
)
from intake.config import get_settings


class UploadService:
    """Service for coordinating binary uploads.
    
    Coordinates:
    - Auth & ownership checks
    - Validation (size, type, state)
    - Encryption of metadata
    - Storage (disk)
    - Persistence (DB)
    - Event logging
    """

    def __init__(
        self,
        quote_repo: QuoteRepository | None = None,
        account_repo: AccountRepository | None = None,
        event_repo: EventRepository | None = None,
        crypto_service: Any | None = None,
        storage_service: Any | None = None,
        validation_service: Any | None = None,
    ):
        self._quote_repo = quote_repo or QuoteRepository()
        self._account_repo = account_repo or AccountRepository()
        self._event_repo = event_repo or EventRepository()
        self._crypto_service = crypto_service or get_crypto_service()
        self._storage_service = storage_service or get_storage_service()
        self._validation_service = validation_service or get_upload_validation_service()
        self._settings = get_settings()

    def handle_upload(self, account_id: str, quote_id: str, upload_file: UploadFile) -> Upload:
        """Handle a file upload for a quote.
        
        Args:
            account_id: ID of the authenticated user
            quote_id: ID of the quote
            upload_file: The uploaded file from FastAPI
            
        Returns:
            The created Upload domain model
            
        Raises:
            HTTPException: If validation or ownership checks fail
        """
        # 1. Fetch quote and verify ownership
        quote = self._quote_repo.get_by_id(quote_id)
        if not quote:
            raise HTTPException(status_code=404, detail="Quote not found")
        
        if quote.account_id != account_id:
            raise HTTPException(status_code=403, detail="Not authorized to upload to this quote")

        # 1.5 Check email verification if required
        if self._settings.intake_require_verified_email_for_uploads:
            account = self._account_repo.get_by_id(account_id)
            if not account or not account.email_verified_at:
                raise HTTPException(status_code=403, detail="Email verification required for uploads")

        # 2. Basic validation (state, count)
        total_bytes = sum(u.size_bytes for u in quote.uploads if u.status == UploadStatus.ACCEPTED)
        try:
            self._validation_service.can_upload_to_quote(
                quote.status, len(quote.uploads), total_bytes
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # 3. File content validation
        # Read content to get size and perform checks
        content = upload_file.file.read()
        size_bytes = len(content)
        
        try:
            extension = self._validation_service.validate_file(
                upload_file.filename, upload_file.content_type, size_bytes
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # 4. Storage
        try:
            storage_object_id, relative_path = self._storage_service.store_file(
                quote_id, content, extension
            )
        except ValueError as e:
            raise HTTPException(status_code=500, detail="Storage failure")

        # 5. Metadata encryption
        encrypted_filename = self._crypto_service.encrypt_string(upload_file.filename)

        # 6. Persistence
        upload = Upload(
            quote_id=quote_id,
            account_id=account_id,
            storage_object_id=storage_object_id,
            storage_relative_path=relative_path,
            encrypted_original_filename=encrypted_filename,
            declared_content_type=upload_file.content_type or "application/octet-stream",
            extension=extension,
            size_bytes=size_bytes,
            status=UploadStatus.ACCEPTED,
        )
        
        # We need a repository method to add an upload to a quote
        # For now, let's assume QuoteRepository has add_upload
        self._quote_repo.add_upload(upload)

        # 7. Event logging
        event = Event.for_quote(
            quote_id=quote_id,
            event_type=EventType.QUOTE_UPLOAD_ACCEPTED,
            actor_type=EventActorType.ACCOUNT,
            actor_id=account_id,
            redacted_summary=f"File upload accepted: {extension} ({size_bytes} bytes)",
        )
        self._event_repo.append(event)

        return upload

    def list_uploads(self, account_id: str, quote_id: str) -> list[Upload]:
        """List all accepted uploads for a quote.
        
        Args:
            account_id: ID of the authenticated user
            quote_id: ID of the quote
            
        Returns:
            List of Upload domain models
        """
        quote = self._quote_repo.get_by_id(quote_id)
        if not quote:
            raise HTTPException(status_code=404, detail="Quote not found")
        
        if quote.account_id != account_id:
            raise HTTPException(status_code=403, detail="Not authorized to view these uploads")

        return [u for u in quote.uploads if u.status == UploadStatus.ACCEPTED]


def get_upload_service() -> UploadService:
    """Get an upload service instance."""
    return UploadService()
