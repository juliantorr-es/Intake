"""Local-only API for the Intake Console."""

from fastapi import APIRouter, Depends, HTTPException
from typing import List, Any
from pydantic import BaseModel

from intake.config import get_settings
from intake.local_console.sync_client import LocalSyncClient
from intake.local_console.review_service import LocalQuoteReviewService, LocalDecryptedQuoteReview
from intake.sync.models import HostedQuoteProjection
from intake.deploy.registry import list_supported_providers

router = APIRouter()

class LocalStatusResponse(BaseModel):
    """Status of the local console and its connection to hosted."""
    hosted_url: str
    sync_auth_configured: bool
    encryption_key_configured: bool
    signing_key_configured: bool
    is_loopback: bool

@router.get("/status", response_model=LocalStatusResponse)
async def get_status():
    """Get status of the local console."""
    settings = get_settings()
    
    # Redact tokens/keys: only show if they exist
    return LocalStatusResponse(
        hosted_url=settings.intake_base_url,
        sync_auth_configured=bool(settings.intake_local_sync_token),
        encryption_key_configured=bool(settings.intake_dev_encryption_key),
        signing_key_configured=bool(settings.intake_local_signing_key),
        is_loopback=True # API should only be reachable via 127.0.0.1
    )

def get_local_review_service() -> LocalQuoteReviewService:
    """Dependency factory for the local review service."""
    return LocalQuoteReviewService()

@router.get("/quotes/pending", response_model=List[HostedQuoteProjection])
async def get_pending_quotes(
    service: LocalQuoteReviewService = Depends(get_local_review_service)
):
    """Get pending quote projections from hosted."""
    try:
        return service.get_pending_reviews()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch from hosted: {e}")

@router.get("/quotes/{quote_id}/review", response_model=LocalDecryptedQuoteReview)
async def get_quote_review(
    quote_id: str,
    service: LocalQuoteReviewService = Depends(get_local_review_service)
):
    """Fetch and decrypt a quote for local review."""
    try:
        return service.get_decrypted_review(quote_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Decryption failed: {e}")

@router.post("/quotes/{quote_id}/start-review")
async def start_quote_review(
    quote_id: str,
    service: LocalQuoteReviewService = Depends(get_local_review_service)
):
    """Transition a quote to reviewing status on hosted."""
    try:
        return service.start_review(quote_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Action failed: {e}")

@router.post("/sync/pull")
async def trigger_sync_pull():
    """Manually trigger a sync pull (placeholder for now)."""
    return {"status": "success", "message": "Sync pull triggered"}
@router.get("/deploy/status")
async def get_deploy_status():
    """Get status of host bootstrapping and deployment."""
    providers = list_supported_providers()
    return {
        "status": "not_configured",
        "supported_providers": [p.value for p in providers],
        "last_deployment": None,
        "recommended_first_step": "scaffold_railway"
    }
