"""Hosted Upload Session Broker Service.

This service is the policy authority for client uploads. It:
- Decides whether a client may upload to a quote
- Chooses the upload provider/route using route decision models
- Creates short-lived upload sessions
- Records upload receipts from providers
- Maintains security: broker chooses provider, client does not
- Never exposes local paths, credentials, or sync tokens
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import HTTPException

from intake.deploy.models_upload import UploadProviderKind, UploadRouteDecision
from intake.deploy.tunnel_adapters.models import TunnelProviderKind
from intake.domain.events import Event, EventActorType, EventType
from intake.domain.quotes import (
    Quote,
    QuoteRepository,
    QuoteStatus,
    UploadReceipt,
    UploadReceiptStatus,
    UploadSession,
    UploadSessionStatus,
)
from intake.domain.time import utc_now
from intake.local_console.receiver.route_decision import UploadRouteDecisionService
from intake.services.quote_service import get_quote_service, QuoteService
from intake.storage.repositories import AccountRepository, EventRepository


# Upload session configuration
UPLOAD_SESSION_DEFAULT_TTL_MINUTES = 30
UPLOAD_SESSION_MAX_FILE_SIZE = 150 * 1024 * 1024  # 150MB
UPLOAD_SESSION_MAX_FILES = 20

# Quote statuses that allow uploads
UPLOAD_ALLOWED_STATUSES = {
    QuoteStatus.DRAFT,
    QuoteStatus.SUBMITTED,
    QuoteStatus.NEEDS_REVIEW,
    QuoteStatus.REVIEWING,
}


class UploadSessionBroker:
    """Hosted upload session broker service.
    
    This is the policy authority for uploads. It:
    - Validates client authentication and ownership
    - Checks quote status allows uploads
    - Selects provider using route decision service
    - Creates upload sessions
    - Processes upload receipts
    - Logs redacted events
    """
    
    def __init__(
        self,
        quote_repo: QuoteRepository | None = None,
        account_repo: AccountRepository | None = None,
        event_repo: EventRepository | None = None,
        route_decision_service: UploadRouteDecisionService | None = None,
        quote_service: QuoteService | None = None,
    ):
        """Initialize the upload session broker."""
        from intake.storage.repositories import QuoteRepository, AccountRepository, EventRepository
        from intake.local_console.receiver.route_decision import UploadRouteDecisionService
        from intake.services.quote_service import QuoteService
        
        self._quote_repo = quote_repo or QuoteRepository()
        self._account_repo = account_repo or AccountRepository()
        self._event_repo = event_repo or EventRepository()
        self._route_decision = route_decision_service or UploadRouteDecisionService()
        self._quote_service = quote_service or get_quote_service()
        
        # Session store: session_id -> UploadSession
        self._sessions: dict[str, UploadSession] = {}
        
        # Receipt store: receipt_id -> UploadReceipt
        self._receipts: dict[str, UploadReceipt] = {}
        
        # Quote to sessions mapping: quote_id -> list[session_id]
        self._quote_sessions: dict[str, list[str]] = {}
        
        # In-memory fallback provider configuration
        self._fallback_provider: Optional[UploadProviderKind] = UploadProviderKind.GOOGLE_DRIVE_FALLBACK_FUTURE
    
    def set_fallback_provider(self, provider: UploadProviderKind | None) -> None:
        """Set the fallback provider (for testing/configuration)."""
        self._fallback_provider = provider
        self._route_decision.set_fallback_provider(provider if provider else None)
    
    # =========================================================================
    # Upload Route
    # =========================================================================
    
    def create_upload_route(
        self,
        quote_id: str,
        account_id: str,
        requested_content_types: list[str] | None = None,
        requested_max_file_size: int | None = None,
    ) -> UploadSession:
        """Create an upload route/session for a quote.
        
        Args:
            quote_id: The quote ID
            account_id: The authenticated account ID
            requested_content_types: Optional list of content types needed
            requested_max_file_size: Optional max file size needed
            
        Returns:
            UploadSession with routing decision
            
        Raises:
            HTTPException: If validation fails (not authenticated, wrong owner, 
                          quote doesn't allow uploads, etc.)
        """
        # 1. Verify quote exists
        quote = self._quote_repo.get_by_id(quote_id)
        if not quote:
            raise HTTPException(status_code=404, detail="Quote not found")
        
        # 2. Verify quote belongs to account
        if quote.account_id != account_id:
            raise HTTPException(
                status_code=403,
                detail="Not authorized to upload to this quote",
            )
        
        # 3. Verify email is verified if required
        account = self._account_repo.get_by_id(account_id)
        if account and not account.email_verified_at:
            from intake.config import get_settings
            settings = get_settings()
            if settings.intake_require_verified_email_for_uploads:
                raise HTTPException(
                    status_code=403,
                    detail="Email verification required for uploads",
                )
        
        # 4. Verify quote status allows uploads
        if quote.status not in UPLOAD_ALLOWED_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"Uploads not allowed for quotes with status: {quote.status.value}",
            )
        
        # 5. Get route decision
        route_decision = self._route_decision.decide_upload_route(
            quote_id=quote_id,
            requested_content_types=requested_content_types or [],
            requested_max_file_size=requested_max_file_size or 0,
            use_fallback=bool(self._fallback_provider),
        )
        
        # 6. Create upload session
        session = UploadSession(
            quote_id=quote_id,
            account_id=account_id,
            chosen_provider=route_decision.chosen_provider,
            route_priority=route_decision.route_priority,
            route_reason=route_decision.route_reason,
            max_file_size_bytes=min(
                requested_max_file_size or UPLOAD_SESSION_MAX_FILE_SIZE,
                UPLOAD_SESSION_MAX_FILE_SIZE,
            ),
            max_files=UPLOAD_SESSION_MAX_FILES,
            upload_endpoint=route_decision.upload_endpoint,
            expires_at=utc_now() + timedelta(minutes=UPLOAD_SESSION_DEFAULT_TTL_MINUTES),
            status=UploadSessionStatus.ACTIVE,
            route_metadata={
                "fallback_available": route_decision.fallback_available,
                "fallback_provider": (
                    route_decision.fallback_provider.value 
                    if route_decision.fallback_provider 
                    else None
                ),
            },
        )
        
        # 7. Store session
        self._sessions[session.id] = session
        if quote_id not in self._quote_sessions:
            self._quote_sessions[quote_id] = []
        self._quote_sessions[quote_id].append(session.id)
        
        # 8. Log event (redacted)
        self._log_event(
            quote_id=quote_id,
            account_id=account_id,
            event_type=EventType.QUOTE_UPLOAD_SESSION_CREATED,
            summary=f"Upload session created for {route_decision.chosen_provider.value}",
        )
        
        return session
    
    # =========================================================================
    # Upload Receipt
    # =========================================================================
    
    def process_upload_receipt(
        self,
        upload_session_id: str,
        provider: UploadProviderKind,
        storage_object_id: str,
        size_bytes: int,
        sha256: str,
        declared_content_type: str,
        extension: str,
        quote_id: Optional[str] = None,
        account_id: Optional[str] = None,
        signature: Optional[str] = None,
        signed_by_device_id: Optional[str] = None,
    ) -> UploadReceipt:
        """Process an upload receipt from a provider.
        
        This endpoint accepts receipts from providers (e.g., Local Receiver)
        confirming file upload completion. Receipts are verified and stored.
        
        Args:
            upload_session_id: The upload session ID from the broker
            provider: The provider that handled the upload
            storage_object_id: Random unguessable ID (NOT original filename)
            size_bytes: File size in bytes
            sha256: SHA256 hash of file content
            declared_content_type: Content type from upload
            extension: File extension (no full filename)
            quote_id: Optional quote ID (for validation)
            account_id: Optional account ID (for validation)
            signature: Optional signature for verification (future)
            signed_by_device_id: Optional device ID that signed (future)
            
        Returns:
            UploadReceipt with assigned ID and metadata
            
        Raises:
            HTTPException: If session is unknown, expired, or validation fails
        """
        # 1. Verify session exists and is valid
        session = self._sessions.get(upload_session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Upload session not found")
        
        # 2. Verify session is not expired
        if session.is_expired():
            raise HTTPException(
                status_code=400,
                detail="Upload session has expired",
            )
        
        # 3. Verify provider matches session's chosen provider
        if provider != session.chosen_provider:
            raise HTTPException(
                status_code=400,
                detail=f"Receipt provider {provider.value} does not match session provider {session.chosen_provider.value}",
            )
        
        # 4. Use session's quote_id and account_id if not provided
        if not quote_id:
            quote_id = session.quote_id
        if not account_id:
            account_id = session.account_id
            
        # 5. Verify quote exists and matches session
        quote = self._quote_repo.get_by_id(quote_id)
        if not quote:
            raise HTTPException(status_code=404, detail="Quote not found")
        if quote.id != session.quote_id:
            raise HTTPException(
                status_code=400,
                detail="Receipt quote does not match session quote",
            )
        
        # 6. Validate file metadata
        if not storage_object_id:
            raise HTTPException(status_code=400, detail="storage_object_id is required")
        if size_bytes <= 0:
            raise HTTPException(status_code=400, detail="size_bytes must be positive")
        if not sha256 or len(sha256) != 64:
            raise HTTPException(status_code=400, detail="Valid SHA256 hash is required")
        if not extension:
            raise HTTPException(status_code=400, detail="extension is required")
        
        # 7. Create receipt
        receipt = UploadReceipt(
            upload_session_id=upload_session_id,
            quote_id=quote_id,
            account_id=account_id,
            provider=provider,
            storage_object_id=storage_object_id,
            size_bytes=size_bytes,
            sha256=sha256,
            declared_content_type=declared_content_type,
            extension=extension,
            status=UploadReceiptStatus.ACCEPTED,
            processed_at=utc_now(),
            signature=signature,
            signed_by_device_id=signed_by_device_id,
        )
        
        # 8. Store receipt
        self._receipts[receipt.id] = receipt
        
        # 9. Update session to mark as having receipts
        # In production, this would update DB; for now, in-memory
        
        # 10. Log event (redacted - no local paths)
        self._log_event(
            quote_id=quote_id,
            account_id=account_id,
            event_type=EventType.QUOTE_UPLOAD_RECEIPT_RECEIVED,
            summary=f"Upload receipt: {extension} ({size_bytes} bytes) from {provider.value}",
        )
        
        return receipt
    
    # =========================================================================
    # Upload List
    # =========================================================================
    
    def list_upload_sessions(
        self,
        quote_id: str,
        account_id: str,
    ) -> list[UploadSession]:
        """List upload sessions for a quote.
        
        Args:
            quote_id: The quote ID
            account_id: The authenticated account ID
            
        Returns:
            List of UploadSession for the quote
            
        Raises:
            HTTPException: If quote not found or not authorized
        """
        # 1. Verify quote exists
        quote = self._quote_repo.get_by_id(quote_id)
        if not quote:
            raise HTTPException(status_code=404, detail="Quote not found")
        
        # 2. Verify ownership
        if quote.account_id != account_id:
            raise HTTPException(
                status_code=403,
                detail="Not authorized to view these upload sessions",
            )
        
        # 3. Return sessions for quote
        session_ids = self._quote_sessions.get(quote_id, [])
        sessions = [self._sessions[sid] for sid in session_ids if sid in self._sessions]
        
        # Filter out expired sessions for clean display
        return [s for s in sessions if not s.is_expired()]
    
    def list_upload_receipts(
        self,
        quote_id: str,
        account_id: str,
    ) -> list[UploadReceipt]:
        """List upload receipts for a quote.
        
        Args:
            quote_id: The quote ID
            account_id: The authenticated account ID
            
        Returns:
            List of UploadReceipt for the quote
            
        Raises:
            HTTPException: If quote not found or not authorized
        """
        # 1. Verify quote exists
        quote = self._quote_repo.get_by_id(quote_id)
        if not quote:
            raise HTTPException(status_code=404, detail="Quote not found")
        
        # 2. Verify ownership
        if quote.account_id != account_id:
            raise HTTPException(
                status_code=403,
                detail="Not authorized to view these upload receipts",
            )
        
        # 3. Return receipts for quote's sessions
        receipts = []
        session_ids = self._quote_sessions.get(quote_id, [])
        for sid in session_ids:
            for rid, receipt in self._receipts.items():
                if receipt.upload_session_id == sid:
                    receipts.append(receipt)
        
        # Sort by received_at descending
        receipts.sort(key=lambda r: r.received_at, reverse=True)
        return receipts
    
    # =========================================================================
    # Internal Helpers
    # =========================================================================
    
    def _log_event(
        self,
        quote_id: str,
        account_id: str,
        event_type: EventType,
        summary: str,
    ) -> None:
        """Log a redacted event.
        
        Args:
            quote_id: The quote ID
            account_id: The account ID
            event_type: The event type
            summary: Redacted summary (no sensitive data)
        """
        try:
            event = Event.for_quote(
                quote_id=quote_id,
                event_type=event_type,
                actor_type=EventActorType.ACCOUNT,
                actor_id=account_id,
                redacted_summary=summary,
            )
            self._event_repo.append(event)
        except Exception:
            # Event logging should not break the main flow
            pass


def get_upload_session_broker() -> UploadSessionBroker:
    """Get the upload session broker singleton."""
    if not hasattr(get_upload_session_broker, "_instance"):
        get_upload_session_broker._instance = UploadSessionBroker()
    return get_upload_session_broker._instance
