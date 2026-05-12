"""Quote intake endpoints."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from intake.domain.projections import SafeQuoteSummary
from intake.domain.time import utc_now
from intake.domain.quotes import QuoteServiceLane, QuoteStatus, Upload
from intake.services.quote_service import get_quote_service, QuoteService
from intake.services.upload_service import get_upload_service, UploadService
from intake.api.deps import get_current_account_id
from fastapi import File, UploadFile

router = APIRouter()


# ========== Request/Response Models ==========


class QuoteStartRequest(BaseModel):
    """Request to start a new quote."""

    service_lane: QuoteServiceLane | None = None


class QuoteStartResponse(BaseModel):
    """Response with new quote ID."""

    quote_id: str
    status: QuoteStatus


class QuoteAnswersRequest(BaseModel):
    """Request to add answers to a quote."""

    short_summary: str | None = None
    detailed_description: str | None = None
    preferred_timeline: str | None = None


class QuoteLocationRequest(BaseModel):
    """Request to add location to a quote."""

    general_service_area: str | None = Field(default=None, description="Non-sensitive service area")
    dev_encrypted_exact_location: dict[str, Any] | None = Field(
        default=None, description="DEV-ONLY mock encrypted exact location payload"
    )




class QuoteSubmitRequest(BaseModel):
    """Request to submit a quote."""

    pass


class QuoteSubmitResponse(BaseModel):
    """Response for quote submission."""

    success: bool
    quote_id: str
    status: QuoteStatus


class QuoteStatusResponse(BaseModel):
    """Response with quote status."""

    quote_id: str
    status: QuoteStatus
    service_lane: QuoteServiceLane | None = None
    general_service_area: str | None = None
    created_at: str


class UploadResponse(BaseModel):
    """Response for an upload."""

    upload_id: str
    quote_id: str
    status: str
    extension: str
    declared_content_type: str
    size_bytes: int
    created_at: str


# ========== Endpoints ==========


@router.post("/start", response_model=QuoteStartResponse)
async def start_quote(
    request: QuoteStartRequest,
    service: QuoteService = Depends(get_quote_service),
) -> QuoteStartResponse:
    """Start a new quote intake."""
    quote = service.create_quote(service_lane=request.service_lane)
    return QuoteStartResponse(
        quote_id=quote.id,
        status=quote.status,
    )


@router.post("/{quote_id}/answers", response_model=QuoteStartResponse)
async def add_answers(
    quote_id: str,
    request: QuoteAnswersRequest,
    service: QuoteService = Depends(get_quote_service),
) -> QuoteStartResponse:
    """Add basic information and answers to a quote."""
    quote = service.add_basic_info(
        quote_id=quote_id,
        short_summary=request.short_summary or "",
        detailed_description=request.detailed_description or "",
        preferred_timeline=request.preferred_timeline,
    )
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    return QuoteStartResponse(
        quote_id=quote.id,
        status=quote.status,
    )


@router.post("/{quote_id}/location", response_model=QuoteStartResponse)
async def add_location(
    quote_id: str,
    request: QuoteLocationRequest,
    account_id: str = Depends(get_current_account_id),
    service: QuoteService = Depends(get_quote_service),
) -> QuoteStartResponse:
    """Add location information to a quote.

    The exact location is encrypted before storage using CryptoService.
    """
    # We use the service to handle encryption and storage
    # If dev_encrypted_exact_location is provided, we extract 'raw' for encryption
    # This maintains compatibility with the current frontend while securing the data.
    exact_location = ""
    if request.dev_encrypted_exact_location:
        exact_location = request.dev_encrypted_exact_location.get("raw") or ""

    updated = service.add_location(
        quote_id=quote_id,
        general_service_area=request.general_service_area or "Unknown",
        exact_location=exact_location,
    )

    if not updated:
        raise HTTPException(status_code=404, detail="Quote not found")

    return QuoteStartResponse(
        quote_id=updated.id,
        status=updated.status,
    )




@router.post("/{quote_id}/submit", response_model=QuoteSubmitResponse)
async def submit_quote(
    quote_id: str,
    request: QuoteSubmitRequest,
    account_id: str = Depends(get_current_account_id),
    service: QuoteService = Depends(get_quote_service),
) -> QuoteSubmitResponse:
    """Submit a quote for review."""
    # Submit the quote ensuring the account owns it
    quote = service.submit_quote(quote_id=quote_id, account_id=account_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found or cannot submit")

    return QuoteSubmitResponse(
        success=True,
        quote_id=quote.id,
        status=quote.status,
    )


@router.get("/{quote_id}/status", response_model=QuoteStatusResponse)
async def get_quote_status(
    quote_id: str,
    service: QuoteService = Depends(get_quote_service),
) -> QuoteStatusResponse:
    """Get the status of a quote."""
    summary = service.get_safe_summary(quote_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Quote not found")

    return QuoteStatusResponse(
        quote_id=quote_id,
        status=QuoteStatus(summary["status"]),
        service_lane=QuoteServiceLane(summary["service_lane"]) if summary.get("service_lane") else None,
        general_service_area=summary.get("general_service_area"),
        created_at=summary["created_at"],
    )


@router.post("/{quote_id}/uploads", response_model=UploadResponse)
async def upload_file(
    quote_id: str,
    file: UploadFile = File(...),
    account_id: str = Depends(get_current_account_id),
    service: UploadService = Depends(get_upload_service),
) -> UploadResponse:
    """Upload a file for a quote."""
    upload = service.handle_upload(account_id, quote_id, file)
    return UploadResponse(**upload.get_safe_summary())


@router.get("/{quote_id}/uploads", response_model=list[UploadResponse])
async def list_uploads(
    quote_id: str,
    account_id: str = Depends(get_current_account_id),
    service: UploadService = Depends(get_upload_service),
) -> list[UploadResponse]:
    """List all uploads for a quote."""
    uploads = service.list_uploads(account_id, quote_id)
    return [UploadResponse(**u.get_safe_summary()) for u in uploads]
