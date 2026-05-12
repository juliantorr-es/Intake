"""Quote intake endpoints."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from intake.domain.projections import SafeQuoteSummary
from intake.domain.quotes import QuoteServiceLane, QuoteStatus
from intake.services.quote_service import get_quote_service, QuoteService

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

    general_service_area: str = Field(..., description="Non-sensitive service area")
    encrypted_exact_location: dict[str, Any] | None = Field(
        default=None, description="Encrypted exact location payload"
    )


class QuoteUploadDeclareRequest(BaseModel):
    """Request to declare an upload."""

    original_filename: str
    content_type: str
    size_bytes: int
    purpose: str = ""


class QuoteUploadDeclareResponse(BaseModel):
    """Response for upload declaration."""

    upload_id: str
    success: bool


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
    service: QuoteService = Depends(get_quote_service),
) -> QuoteStartResponse:
    """Add location information to a quote.

    The exact location is encrypted before storage.
    """
    # For now, we'll just set the general service area
    # In a full implementation, we'd also handle the encrypted payload
    quote = service.add_basic_info(
        quote_id=quote_id,
        short_summary="",
        detailed_description="",
        preferred_timeline=None,
    )
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    quote.general_service_area = request.general_service_area
    quote.updated_at = datetime.utcnow()
    updated = service._repo.update(quote)

    if not updated:
        raise HTTPException(status_code=404, detail="Quote not found")

    return QuoteStartResponse(
        quote_id=updated.id,
        status=updated.status,
    )


@router.post("/{quote_id}/uploads/declare", response_model=QuoteUploadDeclareResponse)
async def declare_upload(
    quote_id: str,
    request: QuoteUploadDeclareRequest,
    service: QuoteService = Depends(get_quote_service),
) -> QuoteUploadDeclareResponse:
    """Declare an upload for a quote.

    This endpoint declares metadata about an upload. Binary upload
    handling is not implemented in this bootstrap slice.
    """
    quote = service.add_upload_declaration(
        quote_id=quote_id,
        original_filename=request.original_filename,
        content_type=request.content_type,
        size_bytes=request.size_bytes,
        purpose=request.purpose,
    )
    if not quote or not quote.upload_declarations:
        raise HTTPException(status_code=404, detail="Quote not found or no upload added")

    latest_upload = quote.upload_declarations[-1]
    return QuoteUploadDeclareResponse(
        upload_id=latest_upload.upload_id,
        success=True,
    )


@router.post("/{quote_id}/submit", response_model=QuoteSubmitResponse)
async def submit_quote(
    quote_id: str,
    request: QuoteSubmitRequest,
    service: QuoteService = Depends(get_quote_service),
) -> QuoteSubmitResponse:
    """Submit a quote for review."""
    # For bootstrap, we don't require account_id
    quote = service.submit_quote(quote_id=quote_id, account_id="bootstrap-account")
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
        created_at=summary["created_at"],
    )
