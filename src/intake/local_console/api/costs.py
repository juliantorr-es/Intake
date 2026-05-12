"""Local Console API for Vendor Cost Ledger.

Endpoints:
- GET /costs/providers - List all available vendors/providers
- POST /costs/estimate - Create a cost estimate scenario
- POST /costs/receipts - Generate a cost receipt from a scenario
- GET /costs/scenarios - List cost estimate scenarios
- GET /costs/scenarios/{scenario_id} - Get a specific scenario
- POST /costs/scenarios/{scenario_id}/line-items - Add line item to scenario
- POST /costs/scenarios/{scenario_id}/assumptions - Add assumption to scenario
- POST /costs/snapshots - Add a source snapshot

Security:
- All endpoints are local-only (not exposed via hosted backend)
- No provider credentials are stored or exposed
- Receipts include disclaimers about pricing changes
"""

from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from intake.costs import (
    CostAssumption,
    CostConfidence,
    CostCurrency,
    CostEstimateLineItem,
    CostEstimateScenario,
    CostFactSourceKind,
    CostFrequency,
    CostRiskLevel,
    CostSourceSnapshot,
    CostCalculator,
    CostCalculatorError,
    VendorCostReceipt,
    VendorProvider,
    VendorProviderKind,
    get_cost_calculator,
)
from intake.domain.time import utc_now

router = APIRouter(prefix="/costs")


# =============================================================================
# Request/Response Models
# =============================================================================

class ProviderListResponse(BaseModel):
    """Response with list of all providers."""
    providers: list[dict[str, Any]] = Field(default_factory=list)


class CreateScenarioRequest(BaseModel):
    """Request to create a new cost estimate scenario."""
    display_name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)


class CreateScenarioResponse(BaseModel):
    """Response with created scenario."""
    scenario_id: str
    display_name: str
    description: str
    created_at: str


class AddLineItemRequest(BaseModel):
    """Request to add a line item to a scenario."""
    provider_kind: str  # VendorProviderKind value
    category: str
    description: str
    quantity: Decimal
    unit_price_usd: Decimal
    frequency: str = "monthly"  # CostFrequency value
    assumption_ids: list[str] = Field(default_factory=list)
    fact_ids: list[str] = Field(default_factory=list)
    snapshot_ids: list[str] = Field(default_factory=list)
    confidence: str = "unknown"  # CostConfidence value
    risk_level: str = "unknown"  # CostRiskLevel value
    notes: str = ""
    sort_order: int = 0


class LineItemResponse(BaseModel):
    """Response with created/updated line item."""
    line_item_id: str
    scenario_id: str
    provider_kind: str
    category: str
    description: str
    quantity: float
    unit_price_usd: float
    total_usd: float
    currency: str
    frequency: str
    confidence: str
    risk_level: str
    notes: str
    created_at: str


class AddAssumptionRequest(BaseModel):
    """Request to add an assumption to a scenario."""
    category: str
    description: str
    data_type: str = "integer"
    value: Any = None
    unit: Optional[str] = None
    confidence: str = "unknown"  # CostConfidence value
    risk_level: str = "unknown"  # CostRiskLevel value
    notes: str = ""
    source: Optional[str] = None
    source_url: Optional[str] = None


class AssumptionResponse(BaseModel):
    """Response with created/updated assumption."""
    assumption_id: str
    scenario_id: str
    category: str
    description: str
    data_type: str
    value: Any
    unit: Optional[str]
    confidence: str
    risk_level: str
    notes: str


class AddSnapshotRequest(BaseModel):
    """Request to add a source snapshot."""
    source_url: str
    source_kind: str = "vendor_website"  # CostFactSourceKind value
    vendor_kind: Optional[str] = None  # VendorProviderKind value
    source_title: Optional[str] = None
    notes: str = ""


class SnapshotResponse(BaseModel):
    """Response with created snapshot."""
    snapshot_id: str
    source_url: str
    source_title: Optional[str]
    captured_at: str
    source_kind: str
    vendor_kind: Optional[str]
    notes: str


class GenerateReceiptRequest(BaseModel):
    """Request to generate a receipt from a scenario."""
    scenario_id: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    valid_until_days: int = 30
    disclaimer: Optional[str] = None
    client_id: Optional[str] = None
    quote_id: Optional[str] = None


class GenerateReceiptResponse(BaseModel):
    """Response with generated receipt."""
    receipt_id: str
    scenario_id: str
    display_name: str
    total_monthly_usd: Optional[float]
    total_one_time_usd: Optional[float]
    total_usd: Optional[float]
    currency: str
    provider_costs_total_usd: Optional[float]
    intake_costs_total_usd: Optional[float]
    provider_costs_breakdown: dict[str, float]
    valid_from: str
    valid_until: Optional[str]
    disclaimer: str
    created_at: str


class ScenarioDetailResponse(BaseModel):
    """Response with full scenario details."""
    scenario_id: str
    display_name: str
    description: str
    total_monthly_usd: Optional[float]
    total_one_time_usd: Optional[float]
    total_usd: Optional[float]
    currency: str
    line_items: list[dict[str, Any]]
    assumptions: list[dict[str, Any]]
    snapshots: list[dict[str, Any]]
    overall_confidence: str
    overall_risk_level: str
    created_at: str
    updated_at: Optional[str]


class ScenarioListResponse(BaseModel):
    """Response with list of scenarios."""
    scenarios: list[dict[str, Any]] = Field(default_factory=list)


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/providers", response_model=ProviderListResponse)
async def list_providers(calculator: CostCalculator = Depends(get_cost_calculator)):
    """List all available vendors/providers.
    
    Returns metadata about all supported providers for cost estimation.
    Does not include credentials or sensitive data.
    """
    providers = calculator.list_providers()
    
    return ProviderListResponse(
        providers=[p.get_safe_display() for p in providers]
    )


@router.post("/scenarios", response_model=CreateScenarioResponse, status_code=status.HTTP_201_CREATED)
async def create_scenario(
    request: CreateScenarioRequest,
    calculator: CostCalculator = Depends(get_cost_calculator),
):
    """Create a new cost estimate scenario.
    
    A scenario is a container for:
    - Line items (individual costs)
    - Assumptions (inputs used in calculations)
    - Source snapshots (where pricing data came from)
    """
    scenario = calculator.create_scenario(
        display_name=request.display_name,
        description=request.description,
        created_by="local_console",  # In production, use authenticated user
    )
    
    # Add tags after creation
    scenario.tags = request.tags
    calculator.update_scenario(scenario)
    
    return CreateScenarioResponse(
        scenario_id=scenario.scenario_id,
        display_name=scenario.display_name,
        description=scenario.description,
        created_at=scenario.created_at.isoformat(),
    )


@router.get("/scenarios", response_model=ScenarioListResponse)
async def list_scenarios(
    calculator: CostCalculator = Depends(get_cost_calculator),
):
    """List all cost estimate scenarios."""
    scenarios = calculator.list_scenarios()
    
    return ScenarioListResponse(
        scenarios=[s.get_safe_display() for s in scenarios]
    )


@router.get("/scenarios/{scenario_id}", response_model=ScenarioDetailResponse)
async def get_scenario(
    scenario_id: str,
    calculator: CostCalculator = Depends(get_cost_calculator),
):
    """Get a specific cost estimate scenario with all details."""
    scenario = calculator.get_scenario(scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    
    return ScenarioDetailResponse(
        scenario_id=scenario.scenario_id,
        display_name=scenario.display_name,
        description=scenario.description,
        total_monthly_usd=float(scenario.total_monthly_usd) if scenario.total_monthly_usd else None,
        total_one_time_usd=float(scenario.total_one_time_usd) if scenario.total_one_time_usd else None,
        total_usd=float(scenario.total_usd) if scenario.total_usd else None,
        currency=scenario.currency.value,
        line_items=[li.get_safe_display() for li in scenario.line_items],
        assumptions=[a.get_safe_display() for a in scenario.assumptions],
        snapshots=[s.get_safe_display() for s in scenario.snapshots],
        overall_confidence=scenario.overall_confidence.value,
        overall_risk_level=scenario.overall_risk_level.value,
        created_at=scenario.created_at.isoformat(),
        updated_at=scenario.updated_at.isoformat() if scenario.updated_at else None,
    )


@router.post("/scenarios/{scenario_id}/line-items", response_model=LineItemResponse, status_code=status.HTTP_201_CREATED)
async def add_line_item(
    scenario_id: str,
    request: AddLineItemRequest,
    calculator: CostCalculator = Depends(get_cost_calculator),
):
    """Add a line item to a scenario.
    
    A line item represents a single cost in the estimate.
    It includes:
    - Provider and category
    - Quantity and unit price
    - Frequency (one-time, monthly, etc.)
    - Links to assumptions and facts
    - Confidence and risk levels
    """
    try:
        line_item = calculator.add_line_item(
            scenario_id=scenario_id,
            provider_kind=VendorProviderKind(request.provider_kind),
            category=request.category,
            description=request.description,
            quantity=request.quantity,
            unit_price_usd=request.unit_price_usd,
            frequency=CostFrequency(request.frequency),
            assumption_ids=request.assumption_ids,
            fact_ids=request.fact_ids,
            snapshot_ids=request.snapshot_ids,
            confidence=CostConfidence(request.confidence),
            risk_level=CostRiskLevel(request.risk_level),
            notes=request.notes,
            sort_order=request.sort_order,
        )
    except CostCalculatorError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return LineItemResponse(
        line_item_id=line_item.line_item_id,
        scenario_id=line_item.scenario_id,
        provider_kind=line_item.provider_kind.value,
        category=line_item.category,
        description=line_item.description,
        quantity=float(line_item.quantity),
        unit_price_usd=float(line_item.unit_price_usd),
        total_usd=float(line_item.total_usd),
        currency=line_item.currency.value,
        frequency=line_item.frequency.value,
        confidence=line_item.confidence.value,
        risk_level=line_item.risk_level.value,
        notes=line_item.notes,
        created_at=line_item.created_at.isoformat(),
    )


@router.post("/scenarios/{scenario_id}/assumptions", response_model=AssumptionResponse, status_code=status.HTTP_201_CREATED)
async def add_assumption(
    scenario_id: str,
    request: AddAssumptionRequest,
    calculator: CostCalculator = Depends(get_cost_calculator),
):
    """Add an assumption to a scenario.
    
    Assumptions are the inputs used in cost calculations.
    Every estimate must include its assumptions.
    
    Examples of assumptions:
    - "10GB of storage needed"
    - "1000 requests per day"
    - "2 CPU cores required"
    - "$0.10 per GB for egress"
    """
    try:
        assumption = calculator.add_assumption(
            scenario_id=scenario_id,
            category=request.category,
            description=request.description,
            data_type=request.data_type,
            value=request.value,
            unit=request.unit,
            confidence=CostConfidence(request.confidence),
            risk_level=CostRiskLevel(request.risk_level),
            notes=request.notes,
            source=request.source,
            source_url=request.source_url,
        )
    except CostCalculatorError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return AssumptionResponse(
        assumption_id=assumption.assumption_id,
        scenario_id=assumption.scenario_id,
        category=assumption.category,
        description=assumption.description,
        data_type=assumption.data_type,
        value=assumption.value,
        unit=assumption.unit,
        confidence=assumption.confidence.value,
        risk_level=assumption.risk_level.value,
        notes=assumption.notes,
    )


@router.post("/snapshots", response_model=SnapshotResponse, status_code=status.HTTP_201_CREATED)
async def add_snapshot(
    request: AddSnapshotRequest,
    calculator: CostCalculator = Depends(get_cost_calculator),
):
    """Add a source snapshot.
    
    A snapshot records that pricing data was obtained from a specific URL
    at a specific time. The actual page content is NOT stored.
    
    This provides an audit trail for where pricing information came from.
    """
    try:
        vendor_kind = VendorProviderKind(request.vendor_kind) if request.vendor_kind else None
        snapshot = calculator.add_snapshot(
            source_url=request.source_url,
            source_kind=CostFactSourceKind(request.source_kind),
            vendor_kind=vendor_kind,
            source_title=request.source_title,
            notes=request.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return SnapshotResponse(
        snapshot_id=snapshot.snapshot_id,
        source_url=snapshot.source_url,
        source_title=snapshot.source_title,
        captured_at=snapshot.captured_at.isoformat(),
        source_kind=snapshot.source_kind.value,
        vendor_kind=snapshot.vendor_kind.value if snapshot.vendor_kind else None,
        notes=snapshot.notes,
    )


@router.post("/receipts", response_model=GenerateReceiptResponse, status_code=status.HTTP_201_CREATED)
async def generate_receipt(
    request: GenerateReceiptRequest,
    calculator: CostCalculator = Depends(get_cost_calculator),
):
    """Generate a cost receipt from a scenario.
    
    The receipt:
    - States pricing may change
    - Separates provider costs from Intake costs
    - Never includes secret/provider credentials
    - Includes source URLs and timestamps
    
    Receipts are useful for:
    - Client quotes
    - Deployment planning documentation
    - Cost comparison between providers
    """
    try:
        disclaimer = request.disclaimer or (
            "Pricing may change. Please verify current rates with vendors. "
            "This estimate is based on publicly available information and assumptions."
        )
        
        receipt = calculator.generate_receipt(
            scenario_id=request.scenario_id,
            display_name=request.display_name,
            description=request.description,
            valid_until_days=request.valid_until_days,
            disclaimer=disclaimer,
            created_by="local_console",
            client_id=request.client_id,
            quote_id=request.quote_id,
        )
    except CostCalculatorError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return GenerateReceiptResponse(
        receipt_id=receipt.receipt_id,
        scenario_id=receipt.scenario_id,
        display_name=receipt.display_name,
        total_monthly_usd=float(receipt.total_monthly_usd) if receipt.total_monthly_usd else None,
        total_one_time_usd=float(receipt.total_one_time_usd) if receipt.total_one_time_usd else None,
        total_usd=float(receipt.total_usd) if receipt.total_usd else None,
        currency=receipt.currency.value,
        provider_costs_total_usd=float(receipt.provider_costs_total_usd) if receipt.provider_costs_total_usd else None,
        intake_costs_total_usd=float(receipt.intake_costs_total_usd) if receipt.intake_costs_total_usd else None,
        provider_costs_breakdown={k: float(v) for k, v in receipt.provider_costs_breakdown.items()},
        valid_from=receipt.valid_from.isoformat(),
        valid_until=receipt.valid_until.isoformat() if receipt.valid_until else None,
        disclaimer=receipt.disclaimer,
        created_at=receipt.created_at.isoformat(),
    )
