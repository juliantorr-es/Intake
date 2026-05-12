"""Receiver API endpoints.

Provides:
- GET /receiver/health
- POST /receiver/handshake
- POST /receiver/uploads/session
- POST /receiver/uploads/{session_id}/file
- POST /receiver/uploads/{session_id}/complete

Bound to 127.0.0.1 only.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.security import HTTPBearer

from intake.local_console.receiver.models import (
    LocalUploadCompleteReceipt,
    LocalUploadReceipt,
    LocalUploadSession,
    LocalUploadSessionCreate,
    ReceiverAvailabilityStatus,
    ReceiverHandshakeChallenge,
    ReceiverHandshakeResponse,
    SessionCompleteRequest,
    UploadFileRequest,
)
from intake.local_console.receiver.service import LocalReceiverService

logger = logging.getLogger(__name__)

# =============================================================================
# Dependency Setup
# =============================================================================

# Security: Bearer token for local authentication (optional for v0)
bearer_scheme = HTTPBearer()


def get_receiver_service() -> LocalReceiverService:
    """Get the receiver service instance."""
    # Use module-level singleton
    if not hasattr(get_receiver_service, "_instance"):
        get_receiver_service._instance = LocalReceiverService()
    return get_receiver_service._instance


# =============================================================================
# Router Setup
# =============================================================================

router = APIRouter(prefix="/receiver", tags=["receiver"])


def create_receiver_app() -> FastAPI:
    """Create a standalone FastAPI app for the receiver.
    
    This can be mounted at /receiver or run as a separate process.
    Bound to 127.0.0.1 only.
    """
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(
        title="Intake Local Receiver",
        description="Local loopback upload receiver for Intake. Separate from Local Console.",
        version="0.1.0",
        openapi_url="/receiver/openapi.json" if True else None,
        docs_url="/receiver/docs" if True else None,
        redoc_url="/receiver/redoc" if True else None,
    )

    # CORS - very restrictive for local dev
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:8000", "http://127.0.0.1:8001", "http://localhost:8000", "http://localhost:8001"],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    app.include_router(router)

    return app


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/health", response_model=ReceiverAvailabilityStatus)
async def health_check(
    service: LocalReceiverService = Depends(get_receiver_service),
) -> ReceiverAvailabilityStatus:
    """Health check endpoint.
    
    Returns safe status information.
    No secrets or filesystem paths are exposed.
    """
    return service.get_availability()


@router.post("/health", response_model=ReceiverAvailabilityStatus)
async def health_check_post(
    service: LocalReceiverService = Depends(get_receiver_service),
) -> ReceiverAvailabilityStatus:
    """Health check endpoint (POST variant for compatibility)."""
    return service.get_availability()


@router.post("/handshake", response_model=ReceiverHandshakeResponse)
async def handshake(
    challenge: ReceiverHandshakeChallenge | None = None,
    service: LocalReceiverService = Depends(get_receiver_service),
) -> ReceiverHandshakeResponse:
    """Perform receiver handshake.
    
    Returns receiver capabilities and status.
    No secrets are included in the response.
    No filesystem paths are exposed.
    local_url is only included in local-dev mode.
    """
    return service.perform_handshake(challenge)


@router.post("/uploads/session", response_model=LocalUploadSession, status_code=status.HTTP_201_CREATED)
async def create_upload_session(
    request: LocalUploadSessionCreate,
    service: LocalReceiverService = Depends(get_receiver_service),
) -> LocalUploadSession:
    """Create a new upload session.
    
    Validates:
    - quote_id is present
    - expires_at is in the future
    - content types are allowed
    - extensions are allowed
    - limits are reasonable
    
    Returns the created session with session_id.
    """
    try:
        session = service.create_session(request)
        return session
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/uploads/session/{session_id}", response_model=LocalUploadSession)
async def get_upload_session(
    session_id: str,
    service: LocalReceiverService = Depends(get_receiver_service),
) -> LocalUploadSession:
    """Get information about an existing upload session."""
    try:
        return service.get_session(session_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.post("/uploads/{session_id}/file", response_model=LocalUploadReceipt)
async def upload_file(
    session_id: str,
    file: Annotated[UploadFile, File()],
    declared_content_type: Annotated[str, Form()],
    original_filename: Annotated[str | None, Form()] = None,
    service: LocalReceiverService = Depends(get_receiver_service),
) -> LocalUploadReceipt:
    """Upload a file to the receiver.
    
    Multipart upload endpoint.
    
    Validates:
    - Session exists and is active
    - File is not empty
    - File size within limits
    - Content type is allowed
    - Extension is allowed
    - Extension matches content type
    - Session limits not exceeded
    
    Stores file with server-generated filename (never uses original).
    Returns public-safe receipt (no local paths exposed).
    
    Note: This loads the file into memory for v0. 
    Future versions should use streaming for large files.
    """
    # Build upload request
    upload_request = UploadFileRequest(
        session_id=session_id,
        declared_content_type=declared_content_type,
        original_filename=original_filename,
    )

    # Read file content
    try:
        file_content = file.file.read()
    except Exception as e:
        logger.error(f"Failed to read file: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to read file content",
        )

    # Process upload
    file_record, rejection = service.process_file_upload(
        session_id=session_id,
        request=upload_request,
        file_content=file_content,
    )

    # Check for rejection
    if rejection:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": rejection.error_message,
                "reason": rejection.reason.value,
                "session_id": rejection.session_id,
            },
        )

    # Build public-safe receipt
    receipt = LocalUploadReceipt(
        upload_id=service.storage.generate_upload_id(),
        session_id=file_record.session_id,
        quote_id=file_record.quote_id,
        file_id=file_record.file_id,
        size_bytes=file_record.size_bytes,
        sha256=file_record.sha256,
        declared_content_type=file_record.declared_content_type,
        extension=file_record.extension,
        stored_at=file_record.stored_at,
        storage_provider=file_record.storage_provider,
    )

    return receipt


@router.post("/uploads/{session_id}/file/stream", response_model=LocalUploadReceipt)
async def upload_file_stream(
    session_id: str,
    file: Annotated[UploadFile, File()],
    declared_content_type: Annotated[str, Form()],
    original_filename: Annotated[str | None, Form()] = None,
    service: LocalReceiverService = Depends(get_receiver_service),
) -> LocalUploadReceipt:
    """Upload a file with streaming (experimental).
    
    This attempts to stream the file rather than loading into memory.
    May still have limitations in v0.
    """
    upload_request = UploadFileRequest(
        session_id=session_id,
        declared_content_type=declared_content_type,
        original_filename=original_filename,
    )

    # Process with streaming
    file_record, rejection = service.process_streamed_file_upload(
        session_id=session_id,
        request=upload_request,
        file_obj=file.file,
    )

    if rejection:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": rejection.error_message,
                "reason": rejection.reason.value,
                "session_id": rejection.session_id,
            },
        )

    receipt = LocalUploadReceipt(
        upload_id=service.storage.generate_upload_id(),
        session_id=file_record.session_id,
        quote_id=file_record.quote_id,
        file_id=file_record.file_id,
        size_bytes=file_record.size_bytes,
        sha256=file_record.sha256,
        declared_content_type=file_record.declared_content_type,
        extension=file_record.extension,
        stored_at=file_record.stored_at,
        storage_provider=file_record.storage_provider,
    )

    return receipt


@router.post("/uploads/{session_id}/complete", response_model=LocalUploadCompleteReceipt)
async def complete_upload_session(
    session_id: str,
    request: SessionCompleteRequest,
    service: LocalReceiverService = Depends(get_receiver_service),
) -> LocalUploadCompleteReceipt:
    """Mark an upload session as complete.
    
    Returns a completion receipt with all file receipts.
    Once completed, no further files can be uploaded to the session.
    """
    if request.session_id != session_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="session_id mismatch in request body",
        )

    try:
        receipt = service.complete_session(request)
        return receipt
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/uploads/{session_id}/receipt")
async def get_session_receipt(
    session_id: str,
    service: LocalReceiverService = Depends(get_receiver_service),
) -> LocalUploadCompleteReceipt:
    """Get the completion receipt for a session.
    
    Only available after session is completed.
    """
    try:
        session = service.get_session(session_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    from intake.local_console.receiver.models import SessionCompleteRequest

    # Build a complete request to generate receipt
    complete_req = SessionCompleteRequest(
        session_id=session_id,
        quote_id=session.quote_id,
    )

    try:
        receipt = service.complete_session(complete_req)
        return receipt
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# =============================================================================
# Standalone Server
# =============================================================================

def run_receiver_server(host: str = "127.0.0.1", port: int = 8001, log_level: str = "info") -> None:
    """Run the receiver as a standalone FastAPI server.
    
    This is the entry point for running the receiver independently.
    Bound to 127.0.0.1 only.
    
    Args:
        host: Host to bind to (MUST be 127.0.0.1 or localhost)
        port: Port to bind to
        log_level: Logging level
    """
    import uvicorn

    # Validate loopback-only
    if host not in ("127.0.0.1", "localhost", "::1"):
        logger.warning("Receiver should only bind to loopback. Normalizing host to 127.0.0.1")
        host = "127.0.0.1"

    # Create app
    app = create_receiver_app()

    # Configure logging
    import logging as log_module
    log_module.basicConfig(level=getattr(log_module, log_level.upper(), log_module.INFO))

    logger.info(f"Starting Local Receiver on {host}:{port}")
    logger.info("Receiver is LOOPBACK ONLY - bound to 127.0.0.1")
    logger.info("Endpoints: /receiver/health, /receiver/handshake, /receiver/uploads/*")

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=log_level,
        reload=False,
        access=True,
    )


# For direct import use
app = create_receiver_app()
