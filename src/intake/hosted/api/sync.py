"""API for synchronization and local device actions."""

from fastapi import APIRouter, Depends, HTTPException, Header, status
from typing import Any
from datetime import datetime, timezone

from intake.config import get_settings
from intake.sync.models import LocalDeviceActionEnvelope, HostedQuoteProjection, EncryptedQuoteEnvelope
from intake.services.signing_service import HostedActionVerificationService
from intake.storage.repositories import SyncRepository, QuoteRepository, EventRepository
from intake.domain.quotes import QuoteStatus
from intake.domain.events import Event, EventAggregateType, EventType, EventActorType
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

async def verify_sync_token(x_intake_sync_token: str = Header(None)):
    """Transport-level authentication for sync endpoints."""
    settings = get_settings()
    if not settings.intake_enable_dev_sync_auth:
        return
    if not x_intake_sync_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing sync token"
        )
    if x_intake_sync_token != settings.intake_local_sync_token.get_secret_value():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid sync token"
        )

from intake.services.quote_service import get_quote_service
from intake.services.event_log import get_event_log_service

@router.get("/quotes/pending", dependencies=[Depends(verify_sync_token)], response_model=list[HostedQuoteProjection])
async def get_pending_quotes(quote_service: Any = Depends(get_quote_service)):
    """Get non-sensitive projections of quotes needing review."""
    quotes = quote_service.get_all_quotes()
    # Filter for those needing review
    pending = [q for q in quotes if q.status in [QuoteStatus.SUBMITTED, QuoteStatus.NEEDS_REVIEW, QuoteStatus.REVIEWING]]
    return [HostedQuoteProjection.from_domain(q) for q in pending]

@router.get("/quotes/{quote_id}/envelope", dependencies=[Depends(verify_sync_token)], response_model=EncryptedQuoteEnvelope)
async def get_quote_envelope(quote_id: str, quote_service: Any = Depends(get_quote_service)):
    """Get the encrypted envelope for a specific quote."""
    quote = quote_service.get_quote(quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    return EncryptedQuoteEnvelope.from_domain(quote)

@router.post("/actions", dependencies=[Depends(verify_sync_token)])
async def process_local_action(
    envelope: LocalDeviceActionEnvelope,
    verify_service: HostedActionVerificationService = Depends(lambda: HostedActionVerificationService()),
    sync_repo: SyncRepository = Depends(lambda: SyncRepository()),
    quote_service: Any = Depends(get_quote_service),
    event_log: Any = Depends(get_event_log_service)
):
    """Verify and process a signed local device action."""
    
    # 1. Get registered device
    device_model = sync_repo.get_device(envelope.device_id)
    if not device_model:
        raise HTTPException(status_code=403, detail=f"Device {envelope.device_id} not registered")
        
    registered_device = device_model.to_domain()
    
    # 2. Verify signature and replay prevention
    try:
        if not verify_service.verify_action(envelope, registered_device):
            logger.error(f"Invalid signature for action {envelope.action_id} from device {envelope.device_id}")
            raise HTTPException(status_code=403, detail="Invalid action signature")
    except ValueError as e:
        logger.error(f"Verification error: {e}")
        raise HTTPException(status_code=403, detail=str(e))
        
    # 3. Dispatch action kind
    if envelope.action_kind == "QUOTE_REVIEW_START":
        return await handle_quote_review_start(envelope, quote_service, event_log)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported action kind: {envelope.action_kind}")

async def handle_quote_review_start(
    envelope: LocalDeviceActionEnvelope,
    quote_service: Any,
    event_log: Any
):
    """Handle QUOTE_REVIEW_START action."""
    if envelope.aggregate_type.lower() != "quote":
        raise HTTPException(status_code=400, detail="Invalid aggregate type for this action")
        
    quote_id = envelope.aggregate_id
    quote = quote_service.get_quote(quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail=f"Quote {quote_id} not found")
        
    # Allowed transitions: submitted -> reviewing, needs_review -> reviewing
    allowed_from = [QuoteStatus.SUBMITTED, QuoteStatus.NEEDS_REVIEW]
    if quote.status not in allowed_from:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot transition from {quote.status} to reviewing"
        )
        
    previous_status = quote.status
    new_status = QuoteStatus.REVIEWING
    
    # Update quote
    # Note: Using the repository directly here since the service might not have a raw status update method 
    # but for pure stabilization we'll stick to the existing repository logic if needed.
    # Actually, let's keep it clean if possible.
    from intake.storage.repositories import QuoteRepository
    QuoteRepository().update_status(quote_id, new_status)
    
    # Append event
    from intake.domain.events import Event, EventAggregateType, EventType, EventActorType
    event = Event(
        aggregate_type=EventAggregateType.QUOTE,
        aggregate_id=quote_id,
        event_type=EventType.QUOTE_REVIEW_STARTED,
        actor_type=EventActorType.OPERATOR,
        actor_id=envelope.device_id,
        redacted_summary=f"Quote moved to reviewing by device {envelope.device_id}",
        encrypted_payload=None # Redacted
    )
    from intake.storage.repositories import EventRepository
    EventRepository().append(event)

    
    return {
        "action_id": envelope.action_id,
        "aggregate_id": quote_id,
        "previous_status": previous_status,
        "new_status": new_status,
        "accepted_at": datetime.now(timezone.utc)
    }
