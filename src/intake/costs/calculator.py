"""Manual Cost Calculator Service.

This service provides manual cost calculation for deployment planning.
It does NOT scrape provider pages automatically - all data is manually
entered or loaded from stored facts.

Key Features:
- Manual cost calculation from known pricing facts
- Assumption tracking for all estimates
- Source snapshot capture (metadata only, not content)
- Receipt generation with disclaimers
- Separation of provider vs Intake costs
"""

import copy
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import uuid4

from intake.costs.models import (
    CostAssumption,
    CostConfidence,
    CostCurrency,
    CostEstimateLineItem,
    CostEstimateScenario,
    CostFactSourceKind,
    CostFrequency,
    CostRiskLevel,
    CostSourceSnapshot,
    CostTimeUnit,
    VendorCostReceipt,
    VendorPricingFact,
    VendorProvider,
    VendorProviderKind,
)
from intake.domain.time import utc_now


# Default validity period for receipts (30 days)
DEFAULT_RECEIPT_VALIDITY_DAYS = 30

# Default disclaimer
DEFAULT_DISCLAIMER = (
    "Pricing may change. Please verify current rates with vendors. "
    "This estimate is based on publicly available information and assumptions. "
    "Actual costs may vary based on usage, region, and vendor pricing changes."
)


class CostCalculatorError(Exception):
    """Error during cost calculation."""
    pass


class CostCalculator:
    """Manual cost calculator for vendor cost estimation.
    
    This calculator:
    - Uses manually entered or stored pricing facts
    - Tracks all assumptions
    - Captures source snapshots
    - Generates timestamped receipts
    - Separates provider costs from Intake costs
    """
    
    def __init__(self):
        """Initialize the calculator."""
        # In-memory fact registry (in production, this would be a database)
        self._facts: dict[str, VendorPricingFact] = {}
        
        # In-memory provider registry
        self._providers: dict[VendorProviderKind, VendorProvider] = {}
        
        # Scenario storage
        self._scenarios: dict[str, CostEstimateScenario] = {}
        
        # Receipt storage
        self._receipts: dict[str, VendorCostReceipt] = {}
        
        # Standalone snapshot storage (snapshots can also be part of scenarios)
        self._snapshots: dict[str, CostSourceSnapshot] = {}
        
        # Initialize with default providers
        self._initialize_default_providers()
    
    def _initialize_default_providers(self) -> None:
        """Initialize with default vendor provider definitions."""
        default_providers = [
            VendorProvider(
                kind=VendorProviderKind.RAILWAY,
                display_name="Railway",
                description="Modern app hosting with generous free tier",
                website_url="https://railway.app",
                pricing_url="https://railway.app/pricing",
                documentation_url="https://docs.railway.app",
                category="hosting",
                supports_manual_calculator=True,
            ),
            VendorProvider(
                kind=VendorProviderKind.RENDER,
                display_name="Render",
                description="Cloud application hosting with free tier",
                website_url="https://render.com",
                pricing_url="https://render.com/pricing",
                documentation_url="https://render.com/docs",
                category="hosting",
                supports_manual_calculator=True,
            ),
            VendorProvider(
                kind=VendorProviderKind.FLY,
                display_name="Fly.io",
                description="Hosting for full stack apps and databases",
                website_url="https://fly.io",
                pricing_url="https://fly.io/docs/about/pricing",
                documentation_url="https://fly.io/docs",
                category="hosting",
                supports_manual_calculator=True,
            ),
            VendorProvider(
                kind=VendorProviderKind.CLOUDFLARE_R2,
                display_name="Cloudflare R2",
                description="S3-compatible object storage",
                website_url="https://www.cloudflare.com/products/r2",
                pricing_url="https://www.cloudflare.com/products/r2/pricing",
                category="storage",
                supports_manual_calculator=True,
            ),
            VendorProvider(
                kind=VendorProviderKind.GOOGLE_DRIVE,
                display_name="Google Drive",
                description="Cloud file storage",
                website_url="https://drive.google.com",
                pricing_url="https://workspace.google.com/pricing.html",
                category="storage",
                supports_manual_calculator=True,
            ),
            VendorProvider(
                kind=VendorProviderKind.TAILSCALE,
                display_name="Tailscale",
                description="Zero config VPN for secure access",
                website_url="https://tailscale.com",
                pricing_url="https://tailscale.com/pricing",
                category="network",
                supports_manual_calculator=True,
            ),
            VendorProvider(
                kind=VendorProviderKind.CLOUDFLARE_TUNNEL,
                display_name="Cloudflare Tunnel",
                description="Secure tunnels for web applications",
                website_url="https://www.cloudflare.com/products/tunnel",
                pricing_url="https://www.cloudflare.com/products/tunnel/pricing",
                category="network",
                supports_manual_calculator=True,
            ),
            VendorProvider(
                kind=VendorProviderKind.SELF_HOSTED,
                display_name="Self-Hosted",
                description="Self-hosted infrastructure",
                category="hosting",
                supports_manual_calculator=True,
            ),
            VendorProvider(
                kind=VendorProviderKind.CUSTOM,
                display_name="Custom",
                description="Custom provider or configuration",
                category="custom",
                supports_manual_calculator=True,
            ),
        ]
        
        for provider in default_providers:
            self._providers[provider.kind] = provider
    
    # =========================================================================
    # Provider Management
    # =========================================================================
    
    def list_providers(self) -> list[VendorProvider]:
        """List all available vendors/providers."""
        return list(self._providers.values())
    
    def get_provider(self, kind: VendorProviderKind) -> Optional[VendorProvider]:
        """Get a specific provider by kind."""
        return self._providers.get(kind)
    
    # =========================================================================
    # Pricing Fact Management
    # =========================================================================
    
    def add_fact(self, fact: VendorPricingFact) -> VendorPricingFact:
        """Add a pricing fact to the registry."""
        self._facts[fact.fact_id] = fact
        return fact
    
    def get_fact(self, fact_id: str) -> Optional[VendorPricingFact]:
        """Get a pricing fact by ID."""
        return self._facts.get(fact_id)
    
    def list_facts(
        self,
        provider_kind: Optional[VendorProviderKind] = None,
        is_active: bool = True,
    ) -> list[VendorPricingFact]:
        """List pricing facts, optionally filtered by provider and active status."""
        facts = list(self._facts.values())
        
        if provider_kind:
            facts = [f for f in facts if f.provider_kind == provider_kind]
        
        if is_active:
            facts = [f for f in facts if f.is_active]
        
        return facts
    
    # =========================================================================
    # Scenario Management
    # =========================================================================
    
    def create_scenario(
        self,
        display_name: str,
        description: str = "",
        created_by: Optional[str] = None,
    ) -> CostEstimateScenario:
        """Create a new cost estimate scenario."""
        scenario = CostEstimateScenario(
            scenario_id=uuid4().hex,
            display_name=display_name,
            description=description,
            created_at=utc_now(),
            created_by=created_by,
        )
        self._scenarios[scenario.scenario_id] = scenario
        return scenario
    
    def get_scenario(self, scenario_id: str) -> Optional[CostEstimateScenario]:
        """Get a scenario by ID."""
        return self._scenarios.get(scenario_id)
    
    def update_scenario(self, scenario: CostEstimateScenario) -> CostEstimateScenario:
        """Update a scenario."""
        self._scenarios[scenario.scenario_id] = scenario
        scenario.updated_at = utc_now()
        return scenario
    
    def delete_scenario(self, scenario_id: str) -> bool:
        """Delete a scenario."""
        if scenario_id in self._scenarios:
            del self._scenarios[scenario_id]
            return True
        return False
    
    def list_scenarios(
        self,
        created_by: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> list[CostEstimateScenario]:
        """List scenarios, optionally filtered."""
        scenarios = list(self._scenarios.values())
        
        if created_by:
            scenarios = [s for s in scenarios if s.created_by == created_by]
        
        if tags:
            scenarios = [s for s in scenarios if any(t in s.tags for t in tags)]
        
        # Sort by created_at descending
        scenarios.sort(key=lambda s: s.created_at, reverse=True)
        return scenarios
    
    # =========================================================================
    # Line Item Calculation
    # =========================================================================
    
    def add_line_item(
        self,
        scenario_id: str,
        provider_kind: VendorProviderKind,
        category: str,
        description: str,
        quantity: Decimal,
        unit_price_usd: Decimal,
        frequency: CostFrequency = CostFrequency.MONTHLY,
        assumption_ids: list[str] | None = None,
        fact_ids: list[str] | None = None,
        snapshot_ids: list[str] | None = None,
        confidence: CostConfidence = CostConfidence.UNKNOWN,
        risk_level: CostRiskLevel = CostRiskLevel.UNKNOWN,
        notes: str = "",
        sort_order: int = 0,
    ) -> CostEstimateLineItem:
        """Add a line item to a scenario."""
        scenario = self.get_scenario(scenario_id)
        if not scenario:
            raise CostCalculatorError(f"Scenario {scenario_id} not found")
        
        total_usd = quantity * unit_price_usd
        
        line_item = CostEstimateLineItem(
            line_item_id=uuid4().hex,
            scenario_id=scenario_id,
            provider_kind=provider_kind,
            category=category,
            description=description,
            quantity=quantity,
            unit_price_usd=unit_price_usd,
            total_usd=total_usd,
            currency=CostCurrency.USD,
            frequency=frequency,
            assumption_ids=assumption_ids or [],
            fact_ids=fact_ids or [],
            snapshot_ids=snapshot_ids or [],
            confidence=confidence,
            risk_level=risk_level,
            notes=notes,
            sort_order=sort_order,
        )
        
        scenario.line_items.append(line_item)
        self.update_scenario(scenario)
        
        # Recalculate totals
        self._recalculate_scenario_totals(scenario)
        
        return line_item
    
    def update_line_item(self, line_item: CostEstimateLineItem) -> CostEstimateLineItem:
        """Update a line item and recalculate scenario totals."""
        scenario = self.get_scenario(line_item.scenario_id)
        if not scenario:
            raise CostCalculatorError(f"Scenario {line_item.scenario_id} not found")
        
        # Find and update the line item
        for i, li in enumerate(scenario.line_items):
            if li.line_item_id == line_item.line_item_id:
                scenario.line_items[i] = line_item
                self.update_scenario(scenario)
                self._recalculate_scenario_totals(scenario)
                return line_item
        
        raise CostCalculatorError(f"Line item {line_item.line_item_id} not found")
    
    def delete_line_item(self, scenario_id: str, line_item_id: str) -> bool:
        """Delete a line item from a scenario."""
        scenario = self.get_scenario(scenario_id)
        if not scenario:
            return False
        
        scenario.line_items = [
            li for li in scenario.line_items if li.line_item_id != line_item_id
        ]
        self.update_scenario(scenario)
        self._recalculate_scenario_totals(scenario)
        return True
    
    def _recalculate_scenario_totals(self, scenario: CostEstimateScenario) -> None:
        """Recalculate all totals for a scenario."""
        monthly_total = Decimal("0")
        one_time_total = Decimal("0")
        
        # Categorize by frequency
        frequency_map = {
            CostFrequency.ONE_TIME: "one_time",
            CostFrequency.HOURLY: "monthly",
            CostFrequency.DAILY: "monthly",
            CostFrequency.WEEKLY: "monthly",
            CostFrequency.MONTHLY: "monthly",
            CostFrequency.YEARLY: "monthly",
            CostFrequency.USAGE_BASED: "monthly",
            CostFrequency.ON_DEMAND: "monthly",
        }
        
        provider_breakdown: dict[str, Decimal] = {}
        
        for line_item in scenario.line_items:
            freq_category = frequency_map.get(line_item.frequency, "monthly")
            
            if freq_category == "one_time":
                one_time_total += line_item.total_usd
            else:
                monthly_total += line_item.total_usd
            
            # Track by provider
            provider_key = line_item.provider_kind.value
            provider_breakdown[provider_key] = provider_breakdown.get(provider_key, Decimal("0")) + line_item.total_usd
        
        scenario.total_monthly_usd = monthly_total
        scenario.total_one_time_usd = one_time_total
        scenario.total_usd = monthly_total + one_time_total
        
        # Update overall confidence/risk
        self._recalculate_scenario_quality(scenario)
    
    def _recalculate_scenario_quality(self, scenario: CostEstimateScenario) -> None:
        """Recalculate overall confidence and risk for a scenario."""
        if not scenario.line_items:
            scenario.overall_confidence = CostConfidence.UNKNOWN
            scenario.overall_risk_level = CostRiskLevel.UNKNOWN
            return
        
        # Get worst confidence and risk across line items
        confidence_order = {
            CostConfidence.VERIFIED: 0,
            CostConfidence.CONFIRMED: 1,
            CostConfidence.ESTIMATED: 2,
            CostConfidence.PROJECTED: 3,
            CostConfidence.UNKNOWN: 4,
        }
        risk_order = {
            CostRiskLevel.LOW: 0,
            CostRiskLevel.MEDIUM: 1,
            CostRiskLevel.HIGH: 2,
            CostRiskLevel.UNCERTAIN: 3,
        }
        
        worst_confidence = scenario.overall_confidence
        worst_risk = scenario.overall_risk_level
        
        for line_item in scenario.line_items:
            if confidence_order.get(line_item.confidence, 4) > confidence_order.get(worst_confidence, 4):
                worst_confidence = line_item.confidence
            if risk_order.get(line_item.risk_level, 3) > risk_order.get(worst_risk, 3):
                worst_risk = line_item.risk_level
        
        scenario.overall_confidence = worst_confidence
        scenario.overall_risk_level = worst_risk
    
    # =========================================================================
    # Assumption Management
    # =========================================================================
    
    def add_assumption(
        self,
        scenario_id: str,
        category: str,
        description: str,
        data_type: str = "integer",
        value: Any = None,
        unit: Optional[str] = None,
        confidence: CostConfidence = CostConfidence.UNKNOWN,
        risk_level: CostRiskLevel = CostRiskLevel.UNKNOWN,
        notes: str = "",
        source: Optional[str] = None,
        source_url: Optional[str] = None,
    ) -> CostAssumption:
        """Add an assumption to a scenario."""
        scenario = self.get_scenario(scenario_id)
        if not scenario:
            raise CostCalculatorError(f"Scenario {scenario_id} not found")
        
        assumption = CostAssumption(
            assumption_id=uuid4().hex,
            scenario_id=scenario_id,
            category=category,
            description=description,
            data_type=data_type,
            value=value,
            unit=unit,
            confidence=confidence,
            risk_level=risk_level,
            notes=notes,
            source=source,
            source_url=source_url,
        )
        
        scenario.assumptions.append(assumption)
        self.update_scenario(scenario)
        return assumption
    
    def update_assumption(self, assumption: CostAssumption) -> CostAssumption:
        """Update an assumption."""
        scenario = self.get_scenario(assumption.scenario_id)
        if not scenario:
            raise CostCalculatorError(f"Scenario {assumption.scenario_id} not found")
        
        for i, a in enumerate(scenario.assumptions):
            if a.assumption_id == assumption.assumption_id:
                scenario.assumptions[i] = assumption
                self.update_scenario(scenario)
                return assumption
        
        raise CostCalculatorError(f"Assumption {assumption.assumption_id} not found")
    
    def delete_assumption(self, scenario_id: str, assumption_id: str) -> bool:
        """Delete an assumption from a scenario."""
        scenario = self.get_scenario(scenario_id)
        if not scenario:
            return False
        
        scenario.assumptions = [
            a for a in scenario.assumptions if a.assumption_id != assumption_id
        ]
        self.update_scenario(scenario)
        return True
    
    # =========================================================================
    # Source Snapshot Management
    # =========================================================================
    
    def add_snapshot(
        self,
        source_url: str,
        source_kind: CostFactSourceKind = CostFactSourceKind.VENDOR_WEBSITE,
        vendor_kind: Optional[VendorProviderKind] = None,
        source_title: Optional[str] = None,
        notes: str = "",
        captured_by: Optional[str] = None,
    ) -> CostSourceSnapshot:
        """Add a source snapshot.
        
        Snapshots are stored both standalone (for listing) and can be
        embedded in scenarios/receipts for context.
        """
        snapshot = CostSourceSnapshot(
            snapshot_id=uuid4().hex,
            source_url=source_url,
            source_title=source_title,
            captured_at=utc_now(),
            source_kind=source_kind,
            vendor_kind=vendor_kind,
            notes=notes,
            captured_by=captured_by,
        )
        # Store in registry for listing
        self._snapshots[snapshot.snapshot_id] = snapshot
        return snapshot
    
    def list_snapshots(self) -> list[CostSourceSnapshot]:
        """List all standalone source snapshots."""
        return list(self._snapshots.values())
    
    def get_snapshot(self, snapshot_id: str) -> Optional[CostSourceSnapshot]:
        """Get a specific snapshot by ID."""
        return self._snapshots.get(snapshot_id)
    
    # =========================================================================
    # Receipt Generation
    # =========================================================================
    
    def generate_receipt(
        self,
        scenario_id: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        valid_until_days: int = DEFAULT_RECEIPT_VALIDITY_DAYS,
        disclaimer: Optional[str] = None,
        created_by: Optional[str] = None,
        client_id: Optional[str] = None,
        quote_id: Optional[str] = None,
    ) -> VendorCostReceipt:
        """Generate a cost receipt from a scenario.
        
        The receipt:
        - States pricing may change
        - Separates provider costs from Intake costs
        - Never includes secret/provider credentials
        - Includes source URLs and timestamps
        """
        scenario = self.get_scenario(scenario_id)
        if not scenario:
            raise CostCalculatorError(f"Scenario {scenario_id} not found")
        
        # Calculate provider breakdown
        provider_breakdown: dict[str, Decimal] = {}
        for line_item in scenario.line_items:
            provider_key = line_item.provider_kind.value
            provider_breakdown[provider_key] = provider_breakdown.get(provider_key, Decimal("0")) + line_item.total_usd
        
        receipt = VendorCostReceipt(
            receipt_id=uuid4().hex,
            scenario_id=scenario_id,
            display_name=display_name or scenario.display_name,
            description=description or scenario.description,
            total_monthly_usd=scenario.total_monthly_usd,
            total_one_time_usd=scenario.total_one_time_usd,
            total_usd=scenario.total_usd,
            currency=scenario.currency,
            provider_costs_total_usd=scenario.total_monthly_usd + scenario.total_one_time_usd,
            intake_costs_total_usd=Decimal("0"),  # Intake costs are separate (not included)
            provider_costs_breakdown=provider_breakdown,
            valid_from=utc_now(),
            valid_until=utc_now() + timedelta(days=valid_until_days),
            disclaimer=disclaimer or DEFAULT_DISCLAIMER,
            created_at=utc_now(),
            created_by=created_by,
            client_id=client_id,
            quote_id=quote_id,
            source_snapshots=scenario.snapshots,
            pricing_updated_at=utc_now(),
        )
        
        self._receipts[receipt.receipt_id] = receipt
        return receipt
    
    def get_receipt(self, receipt_id: str) -> Optional[VendorCostReceipt]:
        """Get a receipt by ID."""
        return self._receipts.get(receipt_id)
    
    def list_receipts(
        self,
        scenario_id: Optional[str] = None,
        created_by: Optional[str] = None,
        client_id: Optional[str] = None,
        quote_id: Optional[str] = None,
    ) -> list[VendorCostReceipt]:
        """List receipts, optionally filtered."""
        receipts = list(self._receipts.values())
        
        if scenario_id:
            receipts = [r for r in receipts if r.scenario_id == scenario_id]
        
        if created_by:
            receipts = [r for r in receipts if r.created_by == created_by]
        
        if client_id:
            receipts = [r for r in receipts if r.client_id == client_id]
        
        if quote_id:
            receipts = [r for r in receipts if r.quote_id == quote_id]
        
        # Sort by created_at descending
        receipts.sort(key=lambda r: r.created_at, reverse=True)
        return receipts
    
    def get_cost_summary_by_provider(
        self,
        scenario_id: str,
    ) -> dict[str, dict[str, Any]]:
        """Get a cost summary broken down by provider."""
        scenario = self.get_scenario(scenario_id)
        if not scenario:
            raise CostCalculatorError(f"Scenario {scenario_id} not found")
        
        result: dict[str, dict[str, Any]] = {}
        
        for line_item in scenario.line_items:
            provider_key = line_item.provider_kind.value
            if provider_key not in result:
                result[provider_key] = {
                    "display_name": line_item.provider_kind.value,
                    "monthly_usd": Decimal("0"),
                    "one_time_usd": Decimal("0"),
                    "total_usd": Decimal("0"),
                    "line_items": [],
                }
            
            result[provider_key]["total_usd"] += line_item.total_usd
            
            if line_item.frequency == CostFrequency.ONE_TIME:
                result[provider_key]["one_time_usd"] += line_item.total_usd
            else:
                result[provider_key]["monthly_usd"] += line_item.total_usd
            
            result[provider_key]["line_items"].append(line_item.get_safe_display())
        
        return result


# Singleton instance
def get_cost_calculator() -> CostCalculator:
    """Get the singleton cost calculator instance."""
    if not hasattr(get_cost_calculator, "_instance"):
        get_cost_calculator._instance = CostCalculator()
    return get_cost_calculator._instance
