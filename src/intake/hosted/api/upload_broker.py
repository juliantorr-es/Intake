"""Hosted Upload Broker API endpoints.

These endpoints provide the hosted upload session broker functionality:
- POST /quotes/{quote_id}/upload-route - Get upload route and create session
- POST /quotes/{quote_id}/uploads/receipt - Submit upload receipt from provider
- GET /quotes/{quote_id}/upload-sessions - List upload sessions for quote
- GET /quotes/{quote_id}/uploads - List upload receipts for quote

Security:
- All endpoints require authenticated client session
- Client cannot choose provider - broker decides based on route decision
- No local paths, credentials, or sync tokens exposed
- Upload receipts do not include original filenames
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from intake.api.deps import get_current_account_id
from intake.deploy.models_upload import UploadProviderKind
from intake.domain.quotes import (
    UploadReceipt,
    UploadReceiptStatus,
    UploadSession,
    UploadSessionStatus,
)
from intake.domain.time import utc_now
from intake.services.upload_session_broker import (
    UploadSessionBroker,
    get_upload_session_broker,
)

router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================

class UploadRouteRequest(BaseModel):
    """Request to get an upload route for a quote.
    
    The client provides metadata about what they want to upload,
    and the broker returns where to upload it.
    """
    # Optional: client can specify what content types they plan to upload
    requested_content_types: list[str] = Field(
        default_factory=list,
        description="Content types the client intends to upload",
    )
    # Optional: client can specify max file size needed
    requested_max_file_size: int = Field(
        default=0,
        description="Maximum file size in bytes needed",
        ge=0,
        le=150 * 1024 * 1024,
    )


class UploadRouteResponse(BaseModel):
    """Response with upload route and session information.
    
    The broker decides the provider and returns session metadata.
    Client uses this to upload directly to the chosen provider.
    """
    # Session information
    upload_session_id: str
    quote_id: str
    provider: str  # UploadProviderKind value
    route_priority: int
    route_reason: str
    
    # Upload constraints
    max_file_size_bytes: int
    max_files: int
    allowed_content_types: list[str]
    allowed_extensions: list[str]
    
    # Routing information
    upload_endpoint: str
    expires_at: str
    status: str  # UploadSessionStatus value
    
    # Metadata (no credentials)
    route_metadata: dict[str, Any] = Field(default_factory=dict)
    
    # Timestamps
    created_at: str


class UploadReceiptRequest(BaseModel):
    """Request to submit an upload receipt from a provider.
    
    This is called by providers (e.g., Local Receiver) to confirm
    file upload completion. Contains verification metadata but NO
    original filenames or absolute local paths.
    """
    # The upload session ID from the broker
    upload_session_id: str
    
    # Provider that handled the upload
    provider: str  # UploadProviderKind value
    
    # File metadata (NO original filename or local paths)
    storage_object_id: str = Field(..., description="Random unguessable ID, not original filename")
    size_bytes: int = Field(..., gt=0, description="File size in bytes")
    sha256: str = Field(..., description="SHA256 hash of file content (64 hex chars)")
    declared_content_type: str = Field(..., description="Content type from upload")
    extension: str = Field(..., description="File extension only, no full filename")
    
    # Optional: quote_id and account_id for validation (can be inferred from session)
    quote_id: str | None = None
    account_id: str | None = None
    
    # Optional: signature for device verification (future)
    signature: str | None = None
    signed_by_device_id: str | None = None


class UploadReceiptResponse(BaseModel):
    """Response for a submitted upload receipt.
    
    Confirms receipt was accepted and provides receipt metadata.
    Does NOT include original filename, local paths, or credentials.
    """
    receipt_id: str
    upload_session_id: str
    quote_id: str
    provider: str
    size_bytes: int
    sha256: str
    declared_content_type: str
    extension: str
    status: str  # UploadReceiptStatus value
    received_at: str


class UploadSessionSummary(BaseModel):
    """Summary of an upload session (safe for client display)."""
    upload_session_id: str
    quote_id: str
    provider: str
    route_priority: int
    route_reason: str
    max_file_size_bytes: int
    max_files: int
    upload_endpoint: str
    expires_at: str
    status: str
    created_at: str


class UploadReceiptSummary(BaseModel):
    """Summary of an upload receipt (safe for client display).
    
    Does NOT include: original filename, local paths, credentials
    """
    receipt_id: str
    upload_session_id: str
    quote_id: str
    provider: str
    size_bytes: int
    declared_content_type: str
    extension: str
    status: str
    received_at: str


class UploadSessionsListResponse(BaseModel):
    """Response with list of upload sessions for a quote."""
    quote_id: str
    sessions: list[UploadSessionSummary] = Field(default_factory=list)


class UploadReceiptsListResponse(BaseModel):
    """Response with list of upload receipts for a quote."""
    quote_id: str
    receipts: list[UploadReceiptSummary] = Field(default_factory=list)


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/{quote_id}/upload-route", response_model=UploadRouteResponse)
async def create_upload_route(
    quote_id: str,
    request: UploadRouteRequest,
    account_id: str = Depends(get_current_account_id),
    broker: UploadSessionBroker = Depends(get_upload_session_broker),
) -> UploadRouteResponse:
    """Create an upload route and session for a quote.
    
    This is the main entry point for client uploads. The broker:
    - Validates authentication and ownership
    - Checks quote status allows uploads
    - Selects provider using route decision models
    - Creates short-lived upload session
    - Returns session metadata to client
    
    Client does NOT choose provider - broker decides.
    
    Security:
    - Requires authenticated client session
    - Requires quote ownership
    - Requires quote status allows uploads
    - Requires verified email if configured
    
    Returns:
    - upload_session_id: Unique session identifier
    - provider: Chosen upload provider (broker decision)
    - upload_endpoint: Where to upload
    - expires_at: Session expiration timestamp
    - All upload constraints and metadata
    """
    # Create upload session via broker
    try:
        session = broker.create_upload_route(
            quote_id=quote_id,
            account_id=account_id,
            requested_content_types=request.requested_content_types,
            requested_max_file_size=request.requested_max_file_size,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating upload route: {str(e)}",
        )
    
    # Return safe response
    return UploadRouteResponse(
        upload_session_id=session.id,
        quote_id=session.quote_id,
        provider=session.chosen_provider.value,
        route_priority=session.route_priority,
        route_reason=session.route_reason,
        max_file_size_bytes=session.max_file_size_bytes,
        max_files=session.max_files,
        allowed_content_types=session.allowed_content_types,
        allowed_extensions=session.allowed_extensions,
        upload_endpoint=session.upload_endpoint,
        expires_at=session.expires_at.isoformat(),
        status=session.status.value,
        route_metadata=session.route_metadata,
        created_at=session.created_at.isoformat(),
    )


@router.post("/{quote_id}/uploads/receipt", response_model=UploadReceiptResponse)
async def submit_upload_receipt(
    quote_id: str,
    request: UploadReceiptRequest,
    broker: UploadSessionBroker = Depends(get_upload_session_broker),
) -> UploadReceiptResponse:
    """Submit an upload receipt from a provider.
    
    This endpoint is called by providers (e.g., Local Receiver) to confirm
    file upload completion. The broker:
    - Validates the receipt
    - Verifies session exists and is valid
    - Verifies provider matches session
    - Stores receipt
    - Logs redacted event
    
    Security:
    - No authentication required from provider (provider presents receipt)
    - Session must exist and not be expired
    - Provider must match session's chosen provider
    - Receipt contains NO original filename or local paths
    
    Note: This is a "push" model where providers push receipts to hosted.
    For production, consider adding signature verification.
    """
    try:
        receipt = broker.process_upload_receipt(
            upload_session_id=request.upload_session_id,
            provider=UploadProviderKind(request.provider),
            storage_object_id=request.storage_object_id,
            size_bytes=request.size_bytes,
            sha256=request.sha256,
            declared_content_type=request.declared_content_type,
            extension=request.extension,
            quote_id=request.quote_id,
            account_id=request.account_id,
            signature=request.signature,
            signed_by_device_id=request.signed_by_device_id,
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing receipt: {str(e)}",
        )
    
    return UploadReceiptResponse(
        receipt_id=receipt.id,
        upload_session_id=receipt.upload_session_id,
        quote_id=receipt.quote_id,
        provider=receipt.provider.value,
        size_bytes=receipt.size_bytes,
        sha256=receipt.sha256,
        declared_content_type=receipt.declared_content_type,
        extension=receipt.extension,
        status=receipt.status.value,
        received_at=receipt.received_at.isoformat(),
    )


@router.get("/{quote_id}/upload-sessions", response_model=UploadSessionsListResponse)
async def list_upload_sessions(
    quote_id: str,
    account_id: str = Depends(get_current_account_id),
    broker: UploadSessionBroker = Depends(get_upload_session_broker),
) -> UploadSessionsListResponse:
    """List upload sessions for a quote.
    
    Returns all active (non-expired) upload sessions for the quote.
    
    Security:
    - Requires authenticated client session
    - Requires quote ownership
    - Returns safe summaries only (no credentials or local paths)
    """
    try:
        sessions = broker.list_upload_sessions(quote_id=quote_id, account_id=account_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing upload sessions: {str(e)}",
        )
    
    return UploadSessionsListResponse(
        quote_id=quote_id,
        sessions=[
            UploadSessionSummary(
                upload_session_id=s.id,
                quote_id=s.quote_id,
                provider=s.chosen_provider.value,
                route_priority=s.route_priority,
                route_reason=s.route_reason,
                max_file_size_bytes=s.max_file_size_bytes,
                max_files=s.max_files,
                upload_endpoint=s.upload_endpoint,
                expires_at=s.expires_at.isoformat(),
                status=s.status.value,
                created_at=s.created_at.isoformat(),
            )
            for s in sessions
        ],
    )


@router.get("/{quote_id}/uploads", response_model=UploadReceiptsListResponse)
async def list_upload_receipts(
    quote_id: str,
    account_id: str = Depends(get_current_account_id),
    broker: UploadSessionBroker = Depends(get_upload_session_broker),
) -> UploadReceiptsListResponse:
    """List upload receipts for a quote.
    
    Returns all upload receipts for the quote's sessions.
    
    Security:
    - Requires authenticated client session
    - Requires quote ownership
    - Returns safe summaries only (no original filenames, local paths, or credentials)
    - SHA256 hashes are truncated in display
    """
    try:
        receipts = broker.list_upload_receipts(quote_id=quote_id, account_id=account_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing upload receipts: {str(e)}",
        )
    
    return UploadReceiptsListResponse(
        quote_id=quote_id,
        receipts=[
            UploadReceiptSummary(
                receipt_id=r.id,
                upload_session_id=r.upload_session_id,
                quote_id=r.quote_id,
                provider=r.provider.value,
                size_bytes=r.size_bytes,
                declared_content_type=r.declared_content_type,
                extension=r.extension,
                status=r.status.value,
                received_at=r.received_at.isoformat(),
            )
            for r in receipts
        ],
    )
