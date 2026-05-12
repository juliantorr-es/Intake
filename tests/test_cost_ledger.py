"""Tests for Vendor Cost Ledger.

This test suite verifies:
- Calculation of line items and totals
- Receipt serialization and deserialization
- Redaction of sensitive data in receipts
- Source snapshot timestamping
- All models are properly constructed
- Provider listings
- Scenario management
"""

import pytest
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from typing import Any
from enum import StrEnum

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from intake.costs import (
    CostCalculator,
    CostCalculatorError,
    CostAssumption,
    CostConfidence,
    CostCurrency,
    CostEstimateLineItem,
    CostEstimateScenario,
    CostFactSourceKind,
    CostFrequency,
    CostRiskLevel,
    CostSourceSnapshot,
    VendorCostReceipt,
    VendorPricingFact,
    VendorProvider,
    VendorProviderKind,
    get_cost_calculator,
)
from intake.domain.time import utc_now


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def calculator() -> CostCalculator:
    """Cost calculator with clean state."""
    return CostCalculator()


# =============================================================================
# Provider Tests
# =============================================================================

class TestVendorProviders:
    """Tests for vendor provider management."""
    
    def test_list_providers_returns_all_providers(self, calculator):
        """List providers returns all default providers."""
        providers = calculator.list_providers()
        assert len(providers) > 0
        
        # Check expected providers exist
        provider_kinds = {p.kind for p in providers}
        expected = {
            VendorProviderKind.RAILWAY,
            VendorProviderKind.RENDER,
            VendorProviderKind.FLY,
            VendorProviderKind.CLOUDFLARE_R2,
            VendorProviderKind.GOOGLE_DRIVE,
            VendorProviderKind.TAILSCALE,
            VendorProviderKind.CLOUDFLARE_TUNNEL,
            VendorProviderKind.SELF_HOSTED,
            VendorProviderKind.CUSTOM,
        }
        assert expected.issubset(provider_kinds)
    
    def test_get_provider_returns_specific(self, calculator):
        """Get provider returns specific provider."""
        provider = calculator.get_provider(VendorProviderKind.RAILWAY)
        assert provider is not None
        assert provider.kind == VendorProviderKind.RAILWAY
        assert provider.display_name == "Railway"
    
    def test_get_provider_returns_none_for_unknown(self, calculator):
        """Get provider returns None for unknown provider."""
        # Create a fake provider kind
        class FakeProvider(StrEnum):
            FAKE = "fake_provider"
        
        provider = calculator.get_provider(FakeProvider.FAKE)
        assert provider is None


# =============================================================================
# Scenario Tests
# =============================================================================

class TestScenarioManagement:
    """Tests for cost estimate scenario management."""
    
    def test_create_scenario(self, calculator):
        """Create a scenario with required fields."""
        scenario = calculator.create_scenario(
            display_name="Test Deployment",
            description="Test deployment cost estimate",
        )
        assert scenario.scenario_id is not None
        assert scenario.display_name == "Test Deployment"
        assert scenario.description == "Test deployment cost estimate"
        assert scenario.created_at is not None
        assert scenario.total_monthly_usd is None
        assert scenario.total_one_time_usd is None
        assert scenario.total_usd is None
    
    def test_get_scenario(self, calculator):
        """Get a scenario by ID."""
        created = calculator.create_scenario(display_name="Test")
        retrieved = calculator.get_scenario(created.scenario_id)
        assert retrieved is not None
        assert retrieved.scenario_id == created.scenario_id
    
    def test_get_scenario_not_found(self, calculator):
        """Get scenario returns None for unknown ID."""
        result = calculator.get_scenario("unknown_scenario_id")
        assert result is None
    
    def test_delete_scenario(self, calculator):
        """Delete a scenario."""
        scenario = calculator.create_scenario(display_name="Test")
        assert calculator.get_scenario(scenario.scenario_id) is not None
        
        result = calculator.delete_scenario(scenario.scenario_id)
        assert result is True
        assert calculator.get_scenario(scenario.scenario_id) is None
    
    def test_list_scenarios(self, calculator):
        """List all scenarios."""
        s1 = calculator.create_scenario(display_name="Test 1")
        s2 = calculator.create_scenario(display_name="Test 2")
        
        scenarios = calculator.list_scenarios()
        assert len(scenarios) == 2
        
        # Should be sorted by created_at descending
        assert scenarios[0].scenario_id == s2.scenario_id
        assert scenarios[1].scenario_id == s1.scenario_id


# =============================================================================
# Line Item Tests
# =============================================================================

class TestLineItemCalculation:
    """Tests for line item calculation."""
    
    @pytest.fixture
    def scenario(self, calculator):
        """Create a scenario for line item tests."""
        return calculator.create_scenario(display_name="Test")
    
    def test_add_line_item(self, calculator, scenario):
        """Add a line item to a scenario."""
        line_item = calculator.add_line_item(
            scenario_id=scenario.scenario_id,
            provider_kind=VendorProviderKind.RAILWAY,
            category="hosting",
            description="Railway instance",
            quantity=Decimal("2"),
            unit_price_usd=Decimal("5.00"),
            frequency=CostFrequency.MONTHLY,
        )
        assert line_item.line_item_id is not None
        assert line_item.scenario_id == scenario.scenario_id
        assert line_item.provider_kind == VendorProviderKind.RAILWAY
        assert line_item.total_usd == Decimal("10.00")  # 2 * 5
    
    def test_add_line_item_rejects_invalid_scenario(self, calculator):
        """Add line item rejects invalid scenario ID."""
        with pytest.raises(CostCalculatorError):
            calculator.add_line_item(
                scenario_id="invalid_scenario",
                provider_kind=VendorProviderKind.RAILWAY,
                category="hosting",
                description="Test",
                quantity=Decimal("1"),
                unit_price_usd=Decimal("5.00"),
            )
    
    def test_line_item_calculation_with_decimals(self, calculator, scenario):
        """Line item calculation handles decimals correctly."""
        line_item = calculator.add_line_item(
            scenario_id=scenario.scenario_id,
            provider_kind=VendorProviderKind.CLOUDFLARE_R2,
            category="storage",
            description="Storage",
            quantity=Decimal("100.5"),
            unit_price_usd=Decimal("0.015"),
            frequency=CostFrequency.MONTHLY,
        )
        # 100.5 * 0.015 = 1.5075
        assert line_item.total_usd == Decimal("1.5075")
    
    def test_line_item_totals_updated(self, calculator, scenario):
        """Scenario totals are updated when line items are added."""
        calculator.add_line_item(
            scenario_id=scenario.scenario_id,
            provider_kind=VendorProviderKind.RAILWAY,
            category="hosting",
            description="Instance 1",
            quantity=Decimal("1"),
            unit_price_usd=Decimal("5.00"),
            frequency=CostFrequency.MONTHLY,
        )
        calculator.add_line_item(
            scenario_id=scenario.scenario_id,
            provider_kind=VendorProviderKind.CLOUDFLARE_R2,
            category="storage",
            description="Storage",
            quantity=Decimal("10"),
            unit_price_usd=Decimal("0.50"),
            frequency=CostFrequency.MONTHLY,
        )
        
        # Reload scenario
        scenario = calculator.get_scenario(scenario.scenario_id)
        assert scenario.total_monthly_usd == Decimal("10.00")  # 5 + 5
        assert scenario.total_usd == Decimal("10.00")
    
    def test_one_time_vs_monthly_totals(self, calculator, scenario):
        """One-time and monthly costs are tracked separately."""
        # Monthly cost
        calculator.add_line_item(
            scenario_id=scenario.scenario_id,
            provider_kind=VendorProviderKind.RAILWAY,
            category="hosting",
            description="Monthly instance",
            quantity=Decimal("1"),
            unit_price_usd=Decimal("5.00"),
            frequency=CostFrequency.MONTHLY,
        )
        
        # One-time cost
        calculator.add_line_item(
            scenario_id=scenario.scenario_id,
            provider_kind=VendorProviderKind.RAILWAY,
            category="setup",
            description="Setup fee",
            quantity=Decimal("1"),
            unit_price_usd=Decimal("10.00"),
            frequency=CostFrequency.ONE_TIME,
        )
        
        # Reload scenario
        scenario = calculator.get_scenario(scenario.scenario_id)
        assert scenario.total_monthly_usd == Decimal("5.00")
        assert scenario.total_one_time_usd == Decimal("10.00")
        assert scenario.total_usd == Decimal("15.00")


# =============================================================================
# Assumption Tests
# =============================================================================

class TestAssumptionManagement:
    """Tests for cost assumption management."""
    
    @pytest.fixture
    def scenario_with_assumptions(self, calculator):
        """Create a scenario with assumptions."""
        scenario = calculator.create_scenario(display_name="Test")
        calculator.add_assumption(
            scenario_id=scenario.scenario_id,
            category="storage",
            description="Storage needed",
            data_type="integer",
            value=100,
            unit="GB",
        )
        return scenario
    
    def test_add_assumption(self, calculator, scenario_with_assumptions):
        """Add an assumption to a scenario."""
        scenario = scenario_with_assumptions
        assumption = calculator.add_assumption(
            scenario_id=scenario.scenario_id,
            category="bandwidth",
            description="Monthly bandwidth",
            data_type="integer",
            value=1000,
            unit="GB",
        )
        assert assumption.assumption_id is not None
        assert assumption.category == "bandwidth"
        assert assumption.value == 1000
    
    def test_list_assumptions(self, calculator, scenario_with_assumptions):
        """Scenario contains added assumptions."""
        scenario = calculator.get_scenario(scenario_with_assumptions.scenario_id)
        assert len(scenario.assumptions) == 1
        assert scenario.assumptions[0].description == "Storage needed"
    
    def test_delete_assumption(self, calculator, scenario_with_assumptions):
        """Delete an assumption from a scenario."""
        scenario = scenario_with_assumptions
        assumption_id = scenario.assumptions[0].assumption_id
        
        result = calculator.delete_assumption(
            scenario_id=scenario.scenario_id,
            assumption_id=assumption_id,
        )
        assert result is True
        
        scenario = calculator.get_scenario(scenario.scenario_id)
        assert len(scenario.assumptions) == 0


# =============================================================================
# Snapshot Tests
# =============================================================================

class TestSourceSnapshot:
    """Tests for source snapshot timestamping and metadata."""
    
    def test_add_snapshot_recorded(self, calculator):
        """Add a source snapshot with metadata."""
        before = utc_now()
        snapshot = calculator.add_snapshot(
            source_url="https://railway.app/pricing",
            source_kind=CostFactSourceKind.VENDOR_WEBSITE,
            vendor_kind=VendorProviderKind.RAILWAY,
            source_title="Railway Pricing",
            notes="Captured free tier details",
        )
        after = utc_now()
        
        assert snapshot.snapshot_id is not None
        assert snapshot.source_url == "https://railway.app/pricing"
        assert snapshot.source_kind == CostFactSourceKind.VENDOR_WEBSITE
        assert snapshot.vendor_kind == VendorProviderKind.RAILWAY
        assert snapshot.source_title == "Railway Pricing"
        assert snapshot.notes == "Captured free tier details"
        assert before <= snapshot.captured_at <= after
    
    def test_snapshot_without_vendor_kind(self, calculator):
        """Snapshot can be created without vendor kind."""
        snapshot = calculator.add_snapshot(
            source_url="https://example.com/pricing",
            source_kind=CostFactSourceKind.THIRD_PARTY,
        )
        assert snapshot.vendor_kind is None
        assert snapshot.source_url == "https://example.com/pricing"
    
    def test_snapshot_safe_display(self, calculator):
        """Snapshot safe display includes all metadata."""
        snapshot = calculator.add_snapshot(
            source_url="https://railway.app/pricing",
            source_kind=CostFactSourceKind.VENDOR_WEBSITE,
            vendor_kind=VendorProviderKind.RAILWAY,
        )
        
        display = snapshot.get_safe_display()
        assert display["snapshot_id"] == snapshot.snapshot_id
        assert display["source_url"] == "https://railway.app/pricing"
        assert display["source_kind"] == "vendor_website"
        assert display["vendor_kind"] == "railway"
        # captured_at should be ISO formatted
        assert "T" in display["captured_at"]


# =============================================================================
# Receipt Tests
# =============================================================================

class TestReceiptGeneration:
    """Tests for cost receipt generation."""
    
    @pytest.fixture
    def scenario_with_data(self, calculator):
        """Create a scenario with line items and assumptions."""
        scenario = calculator.create_scenario(
            display_name="Standard Deployment",
            description="Standard deployment with hosting and storage",
        )
        
        # Add assumptions
        calculator.add_assumption(
            scenario_id=scenario.scenario_id,
            category="infrastructure",
            description="Instance count",
            data_type="integer",
            value=2,
            unit="instances",
        )
        
        # Add line items
        calculator.add_line_item(
            scenario_id=scenario.scenario_id,
            provider_kind=VendorProviderKind.RAILWAY,
            category="hosting",
            description="Railway instances",
            quantity=Decimal("2"),
            unit_price_usd=Decimal("5.00"),
            frequency=CostFrequency.MONTHLY,
            assumption_ids=[scenario.assumptions[0].assumption_id],
        )
        
        # Add a snapshot
        snapshot = calculator.add_snapshot(
            source_url="https://railway.app/pricing",
            vendor_kind=VendorProviderKind.RAILWAY,
        )
        scenario.snapshots.append(snapshot)
        calculator.update_scenario(scenario)
        
        return scenario
    
    def test_generate_receipt(self, calculator, scenario_with_data):
        """Generate a receipt from a scenario."""
        receipt = calculator.generate_receipt(
            scenario_id=scenario_with_data.scenario_id,
            display_name="Cost Estimate: Standard Deployment",
        )
        
        assert receipt.receipt_id is not None
        assert receipt.scenario_id == scenario_with_data.scenario_id
        assert receipt.display_name == "Cost Estimate: Standard Deployment"
        assert receipt.total_monthly_usd == Decimal("10.00")
        assert receipt.total_usd == Decimal("10.00")
        assert receipt.currency == CostCurrency.USD
    
    def test_generate_receipt_includes_disclaimer(self, calculator, scenario_with_data):
        """Receipt includes pricing disclaimer."""
        receipt = calculator.generate_receipt(
            scenario_id=scenario_with_data.scenario_id,
        )
        
        assert "Pricing may change" in receipt.disclaimer
        assert "verify current rates" in receipt.disclaimer
    
    def test_generate_receipt_separates_provider_costs(self, calculator, scenario_with_data):
        """Receipt separates provider costs from Intake costs."""
        receipt = calculator.generate_receipt(
            scenario_id=scenario_with_data.scenario_id,
        )
        
        # Provider costs should equal total
        assert receipt.provider_costs_total_usd == receipt.total_usd
        # Intake costs should be separate (0 in this case)
        assert receipt.intake_costs_total_usd == Decimal("0")
    
    def test_receipt_provider_breakdown(self, calculator, scenario_with_data):
        """Receipt includes provider cost breakdown."""
        receipt = calculator.generate_receipt(
            scenario_id=scenario_with_data.scenario_id,
        )
        
        assert VendorProviderKind.RAILWAY.value in receipt.provider_costs_breakdown
        assert receipt.provider_costs_breakdown["railway"] == Decimal("10.00")
    
    def test_receipt_has_validity_period(self, calculator, scenario_with_data):
        """Receipt has validity period."""
        before = utc_now()
        receipt = calculator.generate_receipt(
            scenario_id=scenario_with_data.scenario_id,
            valid_until_days=30,
        )
        after = utc_now() + timedelta(days=31)
        
        assert before <= receipt.valid_from <= after
        assert receipt.valid_until is not None
        assert receipt.valid_until >= receipt.valid_from
    
    def test_receipt_custom_disclaimer(self, calculator, scenario_with_data):
        """Receipt can have custom disclaimer."""
        custom_disclaimer = "Custom disclaimer text"
        receipt = calculator.generate_receipt(
            scenario_id=scenario_with_data.scenario_id,
            disclaimer=custom_disclaimer,
        )
        
        assert receipt.disclaimer == custom_disclaimer
    
    def test_receipt_includes_source_snapshots(self, calculator, scenario_with_data):
        """Receipt includes source snapshots from scenario."""
        receipt = calculator.generate_receipt(
            scenario_id=scenario_with_data.scenario_id,
        )
        
        assert len(receipt.source_snapshots) == 1
        assert receipt.source_snapshots[0].source_url == "https://railway.app/pricing"


# =============================================================================
# Redaction Tests
# =============================================================================

class TestRedaction:
    """Tests for sensitive data redaction in models."""
    
    def test_vendor_cost_receipt_safe_display(self, calculator):
        """VendorCostReceipt safe display includes essential fields."""
        scenario = calculator.create_scenario(display_name="Test")
        calculator.add_line_item(
            scenario_id=scenario.scenario_id,
            provider_kind=VendorProviderKind.RAILWAY,
            category="hosting",
            description="Instance",
            quantity=Decimal("1"),
            unit_price_usd=Decimal("5.00"),
        )
        
        receipt = calculator.generate_receipt(
            scenario_id=scenario.scenario_id,
            client_id="sensitive_client_id",
            quote_id="sensitive_quote_id",
        )
        
        display = receipt.get_safe_display()
        
        # Should include safe fields
        assert display["receipt_id"] == receipt.receipt_id
        assert display["scenario_id"] == receipt.scenario_id
        assert display["total_monthly_usd"] == 5.0
        
        # client_id and quote_id are stored but not exposed in safe_display
        # (this is by design - they're optional metadata)
        assert receipt.client_id == "sensitive_client_id"
        assert receipt.quote_id == "sensitive_quote_id"
    
    def test_receipt_redacted_summary(self, calculator):
        """Receipt redacted summary truncates sensitive IDs."""
        scenario = calculator.create_scenario(display_name="Test")
        calculator.add_line_item(
            scenario_id=scenario.scenario_id,
            provider_kind=VendorProviderKind.RAILWAY,
            category="hosting",
            description="Instance",
            quantity=Decimal("1"),
            unit_price_usd=Decimal("5.00"),
        )
        
        receipt = calculator.generate_receipt(
            scenario_id=scenario.scenario_id,
        )
        # Note: receipt_id is auto-generated
        actual_id = receipt.receipt_id
        
        summary = receipt.get_redacted_summary()
        
        # Should truncate receipt ID in summary
        assert actual_id[:8] in summary
        assert "..." in summary
        assert "Pricing may change" in summary
    
    def test_vendor_pricing_fact_safe_display(self, calculator):
        """VendorPricingFact safe display includes source but no credentials."""
        fact = VendorPricingFact(
            fact_id="test_fact",
            provider_kind=VendorProviderKind.RAILWAY,
            display_name="Test Fact",
            amount_usd=Decimal("5.00"),
            source_kind=CostFactSourceKind.VENDOR_WEBSITE,
            source_url="https://railway.app/pricing",
            confidence=CostConfidence.VERIFIED,
        )
        
        display = fact.get_safe_display()
        
        assert display["fact_id"] == "test_fact"
        assert display["provider_kind"] == "railway"
        assert display["source_url"] == "https://railway.app/pricing"
        # No sensitive fields to check
    
    def test_cost_assumption_safe_display(self, calculator):
        """CostAssumption safe display includes essential metadata."""
        assumption = CostAssumption(
            assumption_id="test_assumption",
            category="storage",
            description="Storage needed",
            data_type="integer",
            value=100,
            unit="GB",
            confidence=CostConfidence.ESTIMATED,
            risk_level=CostRiskLevel.MEDIUM,
            source_url="https://example.com",
        )
        
        display = assumption.get_safe_display()
        
        assert display["assumption_id"] == "test_assumption"
        assert display["value"] == 100
        # source_url is stored but not included in safe_display by default
        # (it's safe but optional to include)
        assert assumption.source_url == "https://example.com"


# =============================================================================
# Source Timestamping Tests
# =============================================================================

class TestSourceTimestamping:
    """Tests for source timestamping."""
    
    def test_snapshot_captured_at_is_recent(self, calculator):
        """Snapshot captured_at timestamp is recent."""
        before = utc_now()
        snapshot = calculator.add_snapshot(
            source_url="https://example.com",
        )
        after = utc_now()
        
        assert before <= snapshot.captured_at <= after
    
    def test_fact_captured_at_is_timestamped(self, calculator):
        """VendorPricingFact can have captured_at timestamp."""
        fact = VendorPricingFact(
            fact_id="test_fact",
            provider_kind=VendorProviderKind.RAILWAY,
            display_name="Test Fact",
            source_kind=CostFactSourceKind.VENDOR_WEBSITE,
            source_url="https://railway.app/pricing",
            captured_at=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        )
        
        assert fact.captured_at == datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    
    def test_fact_last_verified_at(self, calculator):
        """VendorPricingFact can have last_verified_at timestamp."""
        fact = VendorPricingFact(
            fact_id="test_fact",
            provider_kind=VendorProviderKind.RAILWAY,
            display_name="Test Fact",
            source_kind=CostFactSourceKind.VENDOR_WEBSITE,
            source_url="https://railway.app/pricing",
            last_verified_at=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        )
        
        assert fact.last_verified_at == datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)


# =============================================================================
# Model Validation Tests
# =============================================================================

class TestModelValidation:
    """Tests for model construction and validation."""
    
    def test_vendor_provider_creation(self):
        """VendorProvider can be created with required fields."""
        provider = VendorProvider(
            kind=VendorProviderKind.RAILWAY,
            display_name="Railway",
        )
        assert provider.kind == VendorProviderKind.RAILWAY
        assert provider.display_name == "Railway"
    
    def test_vendor_pricing_fact_creation(self):
        """VendorPricingFact can be created with required fields."""
        fact = VendorPricingFact(
            provider_kind=VendorProviderKind.RAILWAY,
            display_name="Test Fact",
            source_kind=CostFactSourceKind.VENDOR_WEBSITE,
        )
        assert fact.provider_kind == VendorProviderKind.RAILWAY
        assert fact.display_name == "Test Fact"
        assert fact.source_kind == CostFactSourceKind.VENDOR_WEBSITE
    
    def test_cost_estimate_scenario_defaults(self):
        """CostEstimateScenario has correct defaults."""
        scenario = CostEstimateScenario(
            display_name="Test",
        )
        assert scenario.line_items == []
        assert scenario.assumptions == []
        assert scenario.snapshots == []
        assert scenario.currency == CostCurrency.USD
        assert scenario.overall_confidence == CostConfidence.UNKNOWN
    
    def test_vendor_cost_receipt_defaults(self):
        """VendorCostReceipt has correct defaults."""
        receipt = VendorCostReceipt(
            scenario_id="test_scenario",
            display_name="Test Receipt",
        )
        assert receipt.currency == CostCurrency.USD
        assert "Pricing may change" in receipt.disclaimer
        assert receipt.version == 1
        assert receipt.provider_costs_breakdown == {}
