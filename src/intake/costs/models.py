"""Cost Ledger Domain Models.

This module provides models for vendor cost estimation, tracking, and receipt generation.

Key Design Principles:
- Every estimate must include assumptions
- Every provider fact must include source/captured_at or be marked manual
- Receipts must state pricing may change
- Provider costs must be separated from Intake license/support costs
- Secret/provider credentials must never appear in receipts
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum, auto
from typing import Any, Optional

from pydantic import BaseModel, Field, ConfigDict

from intake.domain.time import utc_now


# =============================================================================
# Enums
# =============================================================================

class CostCurrency(StrEnum):
    """Supported currencies for cost estimation."""
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    CAD = "CAD"
    AUD = "AUD"


class CostTimeUnit(StrEnum):
    """Time units for pricing."""
    SECOND = "second"
    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"
    REQUEST = "request"
    GB_MONTH = "GB_month"
    GB = "GB"
    INSTANCE_HOUR = "instance_hour"
    INSTANCE_MONTH = "instance_month"


class CostFrequency(StrEnum):
    """Billing frequency."""
    ONE_TIME = "one_time"
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"
    USAGE_BASED = "usage_based"
    ON_DEMAND = "on_demand"


class VendorProviderKind(StrEnum):
    """Supported vendor/provider kinds for cost estimation."""
    # Hosting Platforms
    RAILWAY = "railway"
    RENDER = "render"
    FLY = "fly"
    
    # Storage
    CLOUDFLARE_R2 = "cloudflare_r2"
    GOOGLE_DRIVE = "google_drive"
    S3 = "s3"
    S3_COMPATIBLE = "s3_compatible"
    
    # Network
    TAILSCALE = "tailscale"
    CLOUDFLARE_TUNNEL = "cloudflare_tunnel"
    
    # Self-hosted
    SELF_HOSTED = "self_hosted"
    
    # Custom/Other
    CUSTOM = "custom"


class CostFactSourceKind(StrEnum):
    """Source kinds for pricing facts."""
    VENDOR_WEBSITE = "vendor_website"
    VENDOR_API = "vendor_api"
    VENDOR_DOCS = "vendor_docs"
    MANUAL_ENTRY = "manual_entry"
    ESTIMATE = "estimate"
    THIRD_PARTY = "third_party"


class CostConfidence(StrEnum):
    """Confidence levels for cost estimates."""
    VERIFIED = "verified"  # Directly from vendor source, recently captured
    CONFIRMED = "confirmed"  # From vendor source, may be slightly outdated
    ESTIMATED = "estimated"  # Based on vendor docs, not official calculator
    PROJECTED = "projected"  # Best-effort projection
    UNKNOWN = "unknown"  # No reliable data available


class CostRiskLevel(StrEnum):
    """Risk levels for cost assumptions."""
    LOW = "low"  # Stable, well-documented pricing
    MEDIUM = "medium"  # Some variability or recent changes
    HIGH = "high"  # Frequent changes or complex pricing
    UNCERTAIN = "uncertain"  # No clear pricing information
    UNKNOWN = "unknown"  # No reliable data available


# =============================================================================
# Models
# =============================================================================

class VendorProvider(BaseModel):
    """Vendor/Provider definition with metadata for cost estimation."""
    model_config = ConfigDict(json_schema_extra={
        "examples": [{
            "kind": "railway",
            "display_name": "Railway",
            "description": "Modern app hosting with generous free tier",
            "website_url": "https://railway.app",
            "pricing_url": "https://railway.app/pricing",
            "documentation_url": "https://docs.railway.app",
            "category": "hosting",
            "supports_manual_calculator": True,
        }]
    })
    
    kind: VendorProviderKind
    display_name: str
    description: str = ""
    website_url: Optional[str] = None
    pricing_url: Optional[str] = None
    documentation_url: Optional[str] = None
    api_url: Optional[str] = None
    category: str = "other"  # hosting, storage, network, etc.
    supports_manual_calculator: bool = True
    supports_api_calculator: bool = False
    is_active: bool = True
    notes: str = ""


class VendorPricingFact(BaseModel):
    """A single pricing fact from a vendor.
    
    Every fact must include source/captured_at or be marked as manual.
    """
    model_config = ConfigDict(json_schema_extra={
        "examples": [{
            "fact_id": "railway_free_dollars",
            "provider_kind": "railway",
            "display_name": "Free Tier Usage Allowance",
            "description": "Monthly free usage allowance",
            "amount_usd": 5.00,
            "currency": "USD",
            "unit": "month",
            "frequency": "monthly",
            "source_kind": "vendor_website",
            "source_url": "https://railway.app/pricing",
            "captured_at": "2024-01-15T10:00:00Z",
            "is_manual": False,
            "confidence": "verified",
        }]
    })
    
    fact_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    provider_kind: VendorProviderKind
    display_name: str
    description: str = ""
    
    # Pricing values
    amount_usd: Optional[Decimal] = None
    amount_min_usd: Optional[Decimal] = None
    amount_max_usd: Optional[Decimal] = None
    currency: CostCurrency = CostCurrency.USD
    
    # Unit information
    unit: Optional[CostTimeUnit] = None
    frequency: Optional[CostFrequency] = None
    
    # tier/bracket information
    tier_name: Optional[str] = None
    min_value: Optional[int] = None  # e.g., min requests, min GB
    max_value: Optional[int] = None  # e.g., max requests, max GB
    
    # Source attribution (REQUIRED)
    source_kind: CostFactSourceKind
    source_url: Optional[str] = None
    source_document_title: Optional[str] = None
    captured_at: Optional[datetime] = None
    
    # Quality indicators
    is_manual: bool = False
    confidence: CostConfidence = CostConfidence.UNKNOWN
    last_verified_at: Optional[datetime] = None
    verification_notes: str = ""
    
    # Validity
    effective_from: Optional[datetime] = None
    effective_until: Optional[datetime] = None
    is_active: bool = True
    
    # Metadata
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: Optional[datetime] = None
    tags: list[str] = Field(default_factory=list)
    
    def get_safe_display(self) -> dict[str, Any]:
        """Return safe display with no sensitive data."""
        return {
            "fact_id": self.fact_id,
            "provider_kind": self.provider_kind.value,
            "display_name": self.display_name,
            "description": self.description,
            "amount_usd": float(self.amount_usd) if self.amount_usd else None,
            "currency": self.currency.value,
            "unit": self.unit.value if self.unit else None,
            "frequency": self.frequency.value if self.frequency else None,
            "source_kind": self.source_kind.value,
            "source_url": self.source_url,
            "confidence": self.confidence.value,
            "is_active": self.is_active,
        }


class CostAssumption(BaseModel):
    """An assumption used in cost estimation.
    
    Every estimate must include its assumptions.
    """
    model_config = ConfigDict(json_schema_extra={
        "examples": [{
            "assumption_id": " requestedStorage_10gb",
            "category": "storage",
            "description": "Total storage needed for client files",
            "data_type": "integer",
            "value": 10,
            "unit": "GB",
            "confidence": "estimated",
            "risk_level": "medium",
            "notes": "Based on average client project size",
        }]
    })
    
    assumption_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    scenario_id: Optional[str] = None
    category: str  # storage, bandwidth, compute, requests, etc.
    description: str
    
    # The assumption value
    data_type: str = "integer"  # integer, decimal, boolean, string, duration
    value: Any  # The actual value (type depends on data_type)
    unit: Optional[str] = None  # Unit of measurement
    
    # Quality indicators
    confidence: CostConfidence = CostConfidence.UNKNOWN
    risk_level: CostRiskLevel = CostRiskLevel.UNKNOWN
    notes: str = ""
    
    # Source
    source: Optional[str] = None  # Where this assumption came from
    source_url: Optional[str] = None
    
    # Validity
    is_active: bool = True
    created_at: datetime = Field(default_factory=utc_now)
    
    def get_safe_display(self) -> dict[str, Any]:
        """Return safe display with no sensitive data."""
        return {
            "assumption_id": self.assumption_id,
            "category": self.category,
            "description": self.description,
            "data_type": self.data_type,
            "value": self.value,
            "unit": self.unit,
            "confidence": self.confidence.value,
            "risk_level": self.risk_level.value,
            "notes": self.notes,
        }


class CostSourceSnapshot(BaseModel):
    """A snapshot of a source (URL) at a point in time.
    
    Captures that we obtained pricing from a specific URL at a specific time.
    Does not store the actual page content (just metadata).
    """
    model_config = ConfigDict(json_schema_extra={
        "examples": [{
            "snapshot_id": "railway_pricing_2024_01_15",
            "source_url": "https://railway.app/pricing",
            "source_title": "Railway Pricing Page",
            "captured_at": "2024-01-15T10:00:00Z",
            "source_kind": "vendor_website",
            "vendor_kind": "railway",
            "notes": "Captured free tier details",
        }]
    })
    
    snapshot_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    source_url: str
    source_title: Optional[str] = None
    captured_at: datetime = Field(default_factory=utc_now)
    source_kind: CostFactSourceKind
    vendor_kind: Optional[VendorProviderKind] = None
    
    # Content hash (optional - could be used to verify snapshot integrity)
    content_hash: Optional[str] = None
    content_length: Optional[int] = None
    
    # Metadata
    notes: str = ""
    captured_by: Optional[str] = None  # operator account or system identifier
    
    def get_safe_display(self) -> dict[str, Any]:
        """Return safe display with no sensitive data."""
        return {
            "snapshot_id": self.snapshot_id,
            "source_url": self.source_url,
            "source_title": self.source_title,
            "captured_at": self.captured_at.isoformat(),
            "source_kind": self.source_kind.value,
            "vendor_kind": self.vendor_kind.value if self.vendor_kind else None,
        }


class CostEstimateLineItem(BaseModel):
    """A single line item in a cost estimate."""
    model_config = ConfigDict(json_schema_extra={
        "examples": [{
            "line_item_id": "hosting_base",
            "scenario_id": "deploy_001",
            "provider_kind": "railway",
            "category": "hosting",
            "description": "Base hosting cost",
            "quantity": 1,
            "unit_price_usd": 5.00,
            "total_usd": 5.00,
            "currency": "USD",
            "frequency": "monthly",
            "assumption_ids": ["instance_count_1"],
            "fact_ids": ["railway_instance_price"],
            "notes": "Includes 1GB RAM, 1 CPU",
        }]
    })
    
    line_item_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    scenario_id: str
    provider_kind: VendorProviderKind
    category: str  # hosting, storage, bandwidth, compute, network, etc.
    description: str
    
    # Calculation
    quantity: Decimal = Decimal("1")
    unit_price_usd: Decimal
    total_usd: Decimal
    currency: CostCurrency = CostCurrency.USD
    frequency: CostFrequency = CostFrequency.MONTHLY
    
    # Formula (optional - how this was calculated)
    formula: Optional[str] = None
    
    # Dependencies
    assumption_ids: list[str] = Field(default_factory=list)
    fact_ids: list[str] = Field(default_factory=list)
    snapshot_ids: list[str] = Field(default_factory=list)
    
    # Quality
    confidence: CostConfidence = CostConfidence.UNKNOWN
    risk_level: CostRiskLevel = CostRiskLevel.UNKNOWN
    notes: str = ""
    
    # Ordering
    sort_order: int = 0
    
    def get_safe_display(self) -> dict[str, Any]:
        """Return safe display with no sensitive data."""
        return {
            "line_item_id": self.line_item_id,
            "scenario_id": self.scenario_id,
            "provider_kind": self.provider_kind.value,
            "category": self.category,
            "description": self.description,
            "quantity": float(self.quantity),
            "unit_price_usd": float(self.unit_price_usd),
            "total_usd": float(self.total_usd),
            "currency": self.currency.value,
            "frequency": self.frequency.value,
            "notes": self.notes,
        }


class CostEstimateScenario(BaseModel):
    """A complete cost estimate scenario.
    
    Contains all line items, assumptions, and source snapshots for a cost estimate.
    """
    model_config = ConfigDict(json_schema_extra={
        "examples": [{
            "scenario_id": "deploy_001",
            "display_name": "Standard Deployment",
            "description": "Standard deployment with Railway hosting, Cloudflare R2 storage",
            "total_monthly_usd": 15.00,
            "currency": "USD",
            "created_at": "2024-01-15T10:00:00Z",
            "line_item_count": 3,
            "assumption_count": 5,
        }]
    })
    
    scenario_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    display_name: str
    description: str = ""
    
    # Totals
    total_monthly_usd: Optional[Decimal] = None
    total_one_time_usd: Optional[Decimal] = None
    total_usd: Optional[Decimal] = None  # Combined total
    currency: CostCurrency = CostCurrency.USD
    
    # Line items
    line_items: list[CostEstimateLineItem] = Field(default_factory=list)
    
    # Assumptions
    assumptions: list[CostAssumption] = Field(default_factory=list)
    
    # Source snapshots
    snapshots: list[CostSourceSnapshot] = Field(default_factory=list)
    
    # Metadata
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None
    
    # Overall quality
    overall_confidence: CostConfidence = CostConfidence.UNKNOWN
    overall_risk_level: CostRiskLevel = CostRiskLevel.UNKNOWN
    risk_notes: str = ""
    
    @property
    def line_item_count(self) -> int:
        """Count of line items."""
        return len(self.line_items)
    
    @property
    def assumption_count(self) -> int:
        """Count of assumptions."""
        return len(self.assumptions)
    
    def get_safe_display(self) -> dict[str, Any]:
        """Return safe display with no sensitive data."""
        return {
            "scenario_id": self.scenario_id,
            "display_name": self.display_name,
            "description": self.description,
            "total_monthly_usd": float(self.total_monthly_usd) if self.total_monthly_usd else None,
            "total_one_time_usd": float(self.total_one_time_usd) if self.total_one_time_usd else None,
            "total_usd": float(self.total_usd) if self.total_usd else None,
            "currency": self.currency.value,
            "line_item_count": self.line_item_count,
            "assumption_count": self.assumption_count,
            "created_at": self.created_at.isoformat(),
        }


class VendorCostReceipt(BaseModel):
    """A timestamped cost receipt for deployment planning.
    
    Receipts must:
    - State pricing may change
    - Separate provider costs from Intake license/support costs
    - Never include secret/provider credentials
    - Include source URLs and timestamps
    """
    model_config = ConfigDict(json_schema_extra={
        "examples": [{
            "receipt_id": "cost_receipt_001",
            "scenario_id": "deploy_001",
            "display_name": "Cost Estimate: Standard Deployment",
            "total_monthly_usd": 15.00,
            "total_one_time_usd": 0.00,
            "currency": "USD",
            "provider_costs_total_usd": 15.00,
            "intake_costs_total_usd": 0.00,
            "created_at": "2024-01-15T10:00:00Z",
            "expires_at": "2024-02-15T10:00:00Z",
            "notes": "Pricing may change. Please verify with vendors.",
        }]
    })
    
    receipt_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    scenario_id: str
    scenario: Optional[CostEstimateScenario] = None  # Can be omitted for serialization
    
    display_name: str
    description: str = ""
    
    # Cost totals
    total_monthly_usd: Optional[Decimal] = None
    total_one_time_usd: Optional[Decimal] = None
    total_usd: Optional[Decimal] = None
    currency: CostCurrency = CostCurrency.USD
    
    # Separated costs (REQUIRED - vendor vs Intake)
    provider_costs_total_usd: Optional[Decimal] = None
    intake_costs_total_usd: Optional[Decimal] = None  # License, support, etc.
    
    # Breakdown by provider (optional)
    provider_costs_breakdown: dict[str, Decimal] = Field(default_factory=dict)
    
    # Validity period
    valid_from: datetime = Field(default_factory=utc_now)
    valid_until: Optional[datetime] = None  # When this estimate is expected to be valid
    
    # Source attribution
    source_snapshots: list[CostSourceSnapshot] = Field(default_factory=list)
    pricing_updated_at: Optional[datetime] = None
    
    # Required disclaimer
    disclaimer: str = "Pricing may change. Please verify current rates with vendors."
    
    # Metadata
    created_at: datetime = Field(default_factory=utc_now)
    created_by: Optional[str] = None
    client_id: Optional[str] = None  # If for a specific client
    quote_id: Optional[str] = None  # If associated with a quote
    
    # Versioning
    version: int = 1
    previous_receipt_id: Optional[str] = None
    
    def get_safe_display(self) -> dict[str, Any]:
        """Return safe display with no sensitive data."""
        return {
            "receipt_id": self.receipt_id,
            "scenario_id": self.scenario_id,
            "display_name": self.display_name,
            "description": self.description,
            "total_monthly_usd": float(self.total_monthly_usd) if self.total_monthly_usd else None,
            "total_one_time_usd": float(self.total_one_time_usd) if self.total_one_time_usd else None,
            "total_usd": float(self.total_usd) if self.total_usd else None,
            "currency": self.currency.value,
            "provider_costs_total_usd": float(self.provider_costs_total_usd) if self.provider_costs_total_usd else None,
            "intake_costs_total_usd": float(self.intake_costs_total_usd) if self.intake_costs_total_usd else None,
            "valid_from": self.valid_from.isoformat(),
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "created_at": self.created_at.isoformat(),
        }
    
    def get_redacted_summary(self) -> str:
        """Return a redacted text summary for logging/display."""
        return (
            f"Cost Receipt {self.receipt_id[:8]}... "
            f"Total: {self.currency.value} {self.total_monthly_usd or 0:.2f}/mo "
            f"({self.line_item_count if hasattr(self, 'line_item_count') else len(self.provider_costs_breakdown)} providers) "
            f"- {self.disclaimer[:50]}..."
        )
