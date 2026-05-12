"""Local Console API for Proof Rail.

Endpoints:
- GET /proof-rail - Get all proof events
- GET /proof-rail/{quote_id} - Get proof events for a specific quote
- GET /proof-rail/sources/{source} - Get events from a specific source
- GET /proof-rail/types/{event_type} - Get events of a specific type

Security:
- All endpoints are local-only (not exposed via hosted backend)
- All event data is redacted
- No sensitive data is exposed
- No encrypted payloads are returned
"""

from typing import Any

from fastapi import APIRouter, Depends

from intake.local_console.services.proof_rail import (
    ProofRail,
    get_proof_rail,
)

router = APIRouter()


@router.get("/", response_model=list[dict[str, Any]])
async def get_proof_rail_events(
    source: str | None = None,
    event_type: str | None = None,
    aggregate_id: str | None = None,
    limit: int = 100,
    proof_rail: ProofRail = Depends(get_proof_rail),
) -> list[dict[str, Any]]:
    """Get proof rail events with optional filters.
    
    Returns a list of redacted proof events from all available sources:
    - Quote events (created, submitted, reviewing, etc.)
    - Upload broker events (sessions created/expired, receipts received)
    - Cost Ledger events (scenarios, receipts, snapshots)
    
    Filters:
    - source: Filter by event source (e.g., "quote_service", "upload_broker", "cost_ledger")
    - event_type: Filter by event type (e.g., "quote_created", "cost_receipt_generated")
    - aggregate_id: Filter by aggregate ID (e.g., quote ID, scenario ID)
    - limit: Maximum number of events to return (default: 100)
    
    All returned events are carefully redacted and do NOT include:
    - Provider credentials or API tokens
    - Private keys, signing keys, or sync tokens
    - Session tokens or verification secrets
    - Local filesystem paths
    - Decrypted client data (location, access notes, questionnaire)
    - Raw ciphertext internals
    - Exact pricing claims (all include "may change" caveats)
    """
    if source and event_type and aggregate_id:
        # Multiple filters - get all and filter
        all_events = proof_rail.get_all_events()
        events = [
            e for e in all_events
            if (source is None or e.source == source) and
               (event_type is None or e.event_type == event_type) and
               (aggregate_id is None or e.aggregate_id == aggregate_id)
        ]
    elif source:
        events = proof_rail.get_events_by_source(source)
    elif event_type:
        events = proof_rail.get_events_by_type(event_type)
    elif aggregate_id:
        events = proof_rail.get_events_by_aggregate(aggregate_id)
    else:
        events = proof_rail.get_all_events()
    
    # Truncate to limit and return list dicts
    return [e.to_list_dict() for e in events[:limit]]


@router.get("/{quote_id}", response_model=list[dict[str, Any]])
async def get_proof_rail_for_quote(
    quote_id: str,
    limit: int = 100,
    proof_rail: ProofRail = Depends(get_proof_rail),
) -> list[dict[str, Any]]:
    """Get proof rail events for a specific quote.
    
    Returns all events related to a specific quote, including:
    - Quote lifecycle events (created, submitted, reviewing, etc.)
    - Upload sessions for this quote
    - Cost receipts associated with this quote
    
    Events are sorted by created_at descending and truncated to limit.
    """
    events = proof_rail.get_events_for_quote(quote_id)
    return [e.to_list_dict() for e in events[:limit]]


@router.get("/sources/{source}", response_model=list[dict[str, Any]])
async def get_proof_rail_by_source(
    source: str,
    limit: int = 100,
    proof_rail: ProofRail = Depends(get_proof_rail),
) -> list[dict[str, Any]]:
    """Get proof rail events from a specific source.
    
    Available sources:
    - quote_service: Quote lifecycle events
    - upload_broker: Upload session events
    - cost_ledger: Cost Ledger events (scenarios, receipts, snapshots)
    """
    events = proof_rail.get_events_by_source(source)
    return [e.to_list_dict() for e in events[:limit]]


@router.get("/types/{event_type}", response_model=list[dict[str, Any]])
async def get_proof_rail_by_type(
    event_type: str,
    limit: int = 100,
    proof_rail: ProofRail = Depends(get_proof_rail),
) -> list[dict[str, Any]]:
    """Get proof rail events of a specific type."""
    events = proof_rail.get_events_by_type(event_type)
    return [e.to_list_dict() for e in events[:limit]]


@router.get("/aggregates/{aggregate_id}", response_model=list[dict[str, Any]])
async def get_proof_rail_by_aggregate(
    aggregate_id: str,
    limit: int = 100,
    proof_rail: ProofRail = Depends(get_proof_rail),
) -> list[dict[str, Any]]:
    """Get proof rail events for a specific aggregate ID.
    
    The aggregate ID can be a quote ID, scenario ID, or any other
    aggregate identifier that events are grouped under.
    """
    events = proof_rail.get_events_by_aggregate(aggregate_id)
    return [e.to_list_dict() for e in events[:limit]]
