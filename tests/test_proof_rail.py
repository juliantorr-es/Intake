"""Tests for Proof Rail service and API.

This test suite verifies:
- Proof Rail aggregates events from multiple sources
- Events are properly redacted
- No secrets, tokens, or sensitive data are exposed
- Event structure is correct
- Filtering works correctly
"""

import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fastapi.testclient import TestClient

from intake.costs import CostCalculator, get_cost_calculator
from intake.costs.models import (
    CostFrequency,
    CostConfidence,
    CostRiskLevel,
    CostFactSourceKind,
    VendorProviderKind,
)
from intake.local_console.services.proof_rail import (
    ProofRail,
    ProofRailEvent,
    ProofRailEventType,
    ProofRailSeverity,
    get_proof_rail,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def calculator() -> CostCalculator:
    """Cost calculator with clean state."""
    return CostCalculator()


@pytest.fixture
def proof_rail(calculator: CostCalculator) -> ProofRail:
    """Proof Rail service with clean state."""
    # Reset the singleton to use our test calculator
    import intake.local_console.services.proof_rail as pr_module
    pr_module._proof_rail = None
    return ProofRail(cost_calculator=calculator)


@pytest.fixture
def api_client() -> TestClient:
    """Test client for Local Console API."""
    from fastapi import FastAPI
    from intake.local_console.api import router as api_router
    app = FastAPI()
    app.include_router(api_router, prefix="/api/local")
    return TestClient(app)


# =============================================================================
# Proof Rail Service Tests
# =============================================================================

class TestProofRailEvents:
    """Tests for Proof Rail event creation and serialization."""
    
    def test_event_creation(self):
        """Proof Rail event can be created with required fields."""
        event = ProofRailEvent(
            event_id="test_event_123",
            event_type=ProofRailEventType.COST_RECEIPT_GENERATED,
            source="cost_ledger",
            aggregate_id="scenario_456",
            aggregate_type="cost_scenario",
        )
        
        assert event.event_id == "test_event_123"
        assert event.event_type == "cost_receipt_generated"
        assert event.source == "cost_ledger"
        assert event.aggregate_id == "scenario_456"
        assert event.aggregate_type == "cost_scenario"
        assert event.severity == ProofRailSeverity.INFO
        assert event.created_at is not None
    
    def test_event_with_all_fields(self):
        """Proof Rail event can include all optional fields."""
        now = datetime.now(timezone.utc)
        event = ProofRailEvent(
            event_id="test_event_123",
            event_type=ProofRailEventType.QUOTE_CREATED,
            source="quote_service",
            aggregate_id="quote_789",
            aggregate_type="quote",
            created_at=now,
            severity=ProofRailSeverity.SUCCESS,
            redacted_summary="Quote created and submitted",
            receipt_ref="receipt_abc",
            details={"key": "value"},
        )
        
        assert event.created_at == now
        assert event.severity == ProofRailSeverity.SUCCESS
        assert event.redacted_summary == "Quote created and submitted"
        assert event.receipt_ref == "receipt_abc"
        assert event.details == {"key": "value"}
    
    def test_event_to_dict_safe(self):
        """Event to_dict includes all safe fields."""
        event = ProofRailEvent(
            event_id="test_event_1234567890abcdef",
            event_type=ProofRailEventType.COST_RECEIPT_GENERATED,
            source="cost_ledger",
            aggregate_id="scenario_1234567890abcdef",
            aggregate_type="cost_scenario",
            severity=ProofRailSeverity.SUCCESS,
            redacted_summary="A" * 300,  # Long summary
            receipt_ref="receipt_1234567890abcdef",
        )
        
        d = event.to_dict()
        
        # IDs should be truncated
        assert len(d["event_id"]) <= 19  # 16 chars + "..."
        assert d["event_id"].endswith("...")
        assert len(d["aggregate_id"]) <= 19
        assert d["aggregate_id"].endswith("...")
        assert len(d["receipt_ref"]) <= 19
        assert d["receipt_ref"].endswith("...")
        
        # Summary should be truncated
        assert len(d["redacted_summary"]) <= 200
        
        # All safe fields present
        assert d["event_type"] == "cost_receipt_generated"
        assert d["source"] == "cost_ledger"
        assert d["severity"] == "success"
        assert "created_at" in d
    
    def test_event_to_list_dict_compact(self):
        """Event to_list_dict returns compact representation."""
        event = ProofRailEvent(
            event_id="test_event_12345678",
            event_type=ProofRailEventType.COST_RECEIPT_GENERATED,
            source="cost_ledger",
            aggregate_id="scenario_123",
            redacted_summary="A" * 200,
        )
        
        d = event.to_list_dict()
        
        # Even shorter truncation
        assert len(d["event_id"]) <= 11  # 8 chars + "..."
        assert d["event_id"].endswith("...")
        assert len(d["summary"]) <= 100
        
        assert d["event_type"] == "cost_receipt_generated"
        assert d["source"] == "cost_ledger"
        assert d["severity"] == "info"


class TestProofRailService:
    """Tests for Proof Rail service aggregation."""
    
    def test_get_all_events_empty(self, proof_rail: ProofRail):
        """Get all events returns empty list when no data."""
        # With no data in the calculator, we should still get an empty list
        events = proof_rail.get_all_events()
        # May have events from other sources, but at minimum no errors
        assert isinstance(events, list)
    
    def test_get_all_events_with_cost_scenarios(self, proof_rail: ProofRail, calculator: CostCalculator):
        """Get all events includes cost ledger scenarios."""
        # Create a scenario
        scenario = calculator.create_scenario(
            display_name="Test Scenario",
            description="Test description",
        )
        
        events = proof_rail.get_all_events()
        
        # Should have at least our scenario event
        scenario_events = [e for e in events if e.event_type == ProofRailEventType.COST_SCENARIO_CREATED]
        assert len(scenario_events) >= 1
        
        # Check the event
        event = scenario_events[0]
        assert event.source == "cost_ledger"
        assert event.aggregate_id == scenario.scenario_id
        assert event.aggregate_type == "cost_scenario"
    
    def test_get_all_events_with_cost_receipts(self, proof_rail: ProofRail, calculator: CostCalculator):
        """Get all events includes cost ledger receipts."""
        # Create a scenario with line items
        scenario = calculator.create_scenario(
            display_name="Test Scenario",
        )
        calculator.add_line_item(
            scenario_id=scenario.scenario_id,
            provider_kind=VendorProviderKind.RAILWAY,
            category="hosting",
            description="Test instance",
            quantity=Decimal("1"),
            unit_price_usd=Decimal("5.00"),
            frequency=CostFrequency.MONTHLY,
        )
        
        # Generate receipt
        receipt = calculator.generate_receipt(
            scenario_id=scenario.scenario_id,
            display_name="Test Receipt",
        )
        
        events = proof_rail.get_all_events()
        
        # Should have receipt event
        receipt_events = [e for e in events if e.event_type == ProofRailEventType.COST_RECEIPT_GENERATED]
        assert len(receipt_events) >= 1
        
        event = receipt_events[0]
        assert event.source == "cost_ledger"
        assert event.aggregate_id == scenario.scenario_id
        assert event.receipt_ref == receipt.receipt_id
    
    def test_get_all_events_with_snapshots(self, proof_rail: ProofRail, calculator: CostCalculator):
        """Get all events includes cost ledger snapshots."""
        # Create a snapshot
        snapshot = calculator.add_snapshot(
            source_url="https://example.com/pricing",
            source_kind=CostFactSourceKind.VENDOR_WEBSITE,
            vendor_kind=VendorProviderKind.RAILWAY,
        )
        
        events = proof_rail.get_all_events()
        
        # Should have snapshot event
        snapshot_events = [e for e in events if e.event_type == ProofRailEventType.COST_SNAPSHOT_CREATED]
        assert len(snapshot_events) >= 1
        
        event = snapshot_events[0]
        assert event.source == "cost_ledger"
        assert event.aggregate_type == "provider"
    
    def test_filter_by_source(self, proof_rail: ProofRail, calculator: CostCalculator):
        """Filter events by source works correctly."""
        # Create a scenario
        calculator.create_scenario(display_name="Test")
        
        # Filter for cost_ledger source
        events = proof_rail.get_events_by_source("cost_ledger")
        
        assert isinstance(events, list)
        for event in events:
            assert event.source == "cost_ledger"
    
    def test_filter_by_type(self, proof_rail: ProofRail, calculator: CostCalculator):
        """Filter events by type works correctly."""
        # Create a scenario
        calculator.create_scenario(display_name="Test")
        
        # Filter for scenario created events
        events = proof_rail.get_events_by_type(ProofRailEventType.COST_SCENARIO_CREATED)
        
        assert isinstance(events, list)
        for event in events:
            assert event.event_type == ProofRailEventType.COST_SCENARIO_CREATED
    
    def test_filter_by_aggregate(self, proof_rail: ProofRail, calculator: CostCalculator):
        """Filter events by aggregate ID works correctly."""
        # Create a scenario
        scenario = calculator.create_scenario(display_name="Test Aggregate")
        
        # Filter by scenario ID
        events = proof_rail.get_events_by_aggregate(scenario.scenario_id)
        
        assert isinstance(events, list)
        for event in events:
            assert event.aggregate_id == scenario.scenario_id
    
    def test_events_sorted_by_date(self, proof_rail: ProofRail, calculator: CostCalculator):
        """Events are sorted by created_at descending."""
        # Create multiple scenarios
        scenario1 = calculator.create_scenario(display_name="First")
        scenario2 = calculator.create_scenario(display_name="Second")
        
        events = proof_rail.get_all_events()
        cost_events = [e for e in events if e.source == "cost_ledger"]
        
        # Check that newer events come first
        if len(cost_events) >= 2:
            assert cost_events[0].created_at >= cost_events[1].created_at


# =============================================================================
# Proof Rail Redaction Tests
# =============================================================================

class TestProofRailRedaction:
    """Tests for sensitive data redaction in Proof Rail events."""
    
    def test_event_id_truncated_in_dict(self, proof_rail: ProofRail):
        """Long event IDs are truncated in to_dict."""
        event = ProofRailEvent(
            event_id="a" * 100,
            event_type=ProofRailEventType.COST_RECEIPT_GENERATED,
            source="cost_ledger",
        )
        
        d = event.to_dict()
        assert len(d["event_id"]) <= 19
        assert d["event_id"].endswith("...")
    
    def test_aggregate_id_truncated_in_dict(self, proof_rail: ProofRail):
        """Long aggregate IDs are truncated in to_dict."""
        event = ProofRailEvent(
            event_id="test",
            event_type=ProofRailEventType.COST_RECEIPT_GENERATED,
            source="cost_ledger",
            aggregate_id="a" * 100,
        )
        
        d = event.to_dict()
        assert len(d["aggregate_id"]) <= 19
        assert d["aggregate_id"].endswith("...")
    
    def test_summary_truncated_in_dict(self, proof_rail: ProofRail):
        """Long summaries are truncated in to_dict."""
        event = ProofRailEvent(
            event_id="test",
            event_type=ProofRailEventType.COST_RECEIPT_GENERATED,
            source="cost_ledger",
            redacted_summary="a" * 1000,
        )
        
        d = event.to_dict()
        assert len(d["redacted_summary"]) <= 200
    
    def test_event_id_short_in_list_dict(self, proof_rail: ProofRail):
        """Event IDs are even shorter in to_list_dict."""
        event = ProofRailEvent(
            event_id="a" * 100,
            event_type=ProofRailEventType.COST_RECEIPT_GENERATED,
            source="cost_ledger",
        )
        
        d = event.to_list_dict()
        assert len(d["event_id"]) <= 11
        assert d["event_id"].endswith("...")
    
    def test_summary_truncated_in_list_dict(self, proof_rail: ProofRail):
        """Summaries are truncated in to_list_dict."""
        event = ProofRailEvent(
            event_id="test",
            event_type=ProofRailEventType.COST_RECEIPT_GENERATED,
            source="cost_ledger",
            redacted_summary="a" * 1000,
        )
        
        d = event.to_list_dict()
        assert len(d["summary"]) <= 100
    
    def test_no_sensitive_data_in_event(self, proof_rail: ProofRail):
        """Events never include sensitive data fields."""
        # Create event with potentially sensitive data
        event = ProofRailEvent(
            event_id="test",
            event_type=ProofRailEventType.COST_RECEIPT_GENERATED,
            source="cost_ledger",
            aggregate_id="some_id",
            redacted_summary="Some summary",
            receipt_ref="some_receipt",
        )
        
        d = event.to_dict()
        
        # Check that no sensitive fields are present
        sensitive_fields = ["password", "token", "secret", "key", "credential", "ssn", "credit_card"]
        for field in sensitive_fields:
            assert field not in d
        
        # Check that encrypted_payload is not exposed
        assert "encrypted_payload" not in d
    
    def test_receipt_ref_truncated(self, proof_rail: ProofRail):
        """Long receipt refs are truncated."""
        event = ProofRailEvent(
            event_id="test",
            event_type=ProofRailEventType.COST_RECEIPT_GENERATED,
            source="cost_ledger",
            receipt_ref="a" * 100,
        )
        
        d = event.to_dict()
        assert len(d["receipt_ref"]) <= 19
        assert d["receipt_ref"].endswith("...")


# =============================================================================
# Proof Rail API Tests
# =============================================================================

class TestProofRailAPI:
    """Tests for Proof Rail API endpoints."""
    
    def test_get_proof_rail_events_endpoint_exists(self, api_client: TestClient):
        """GET /api/local/proof-rail endpoint exists."""
        response = api_client.get("/api/local/proof-rail")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_get_proof_rail_with_filters(self, api_client: TestClient):
        """GET /api/local/proof-rail accepts filters."""
        response = api_client.get("/api/local/proof-rail?source=cost_ledger")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        
        response = api_client.get("/api/local/proof-rail?event_type=cost_scenario_created")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_get_proof_rail_for_quote_endpoint(self, api_client: TestClient):
        """GET /api/local/proof-rail/{quote_id} endpoint exists."""
        response = api_client.get("/api/local/proof-rail/quote_123")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_get_proof_rail_by_source_endpoint(self, api_client: TestClient):
        """GET /api/local/proof-rail/sources/{source} endpoint exists."""
        response = api_client.get("/api/local/proof-rail/sources/cost_ledger")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_get_proof_rail_by_type_endpoint(self, api_client: TestClient):
        """GET /api/local/proof-rail/types/{event_type} endpoint exists."""
        response = api_client.get("/api/local/proof-rail/types/cost_scenario_created")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_get_proof_rail_by_aggregate_endpoint(self, api_client: TestClient):
        """GET /api/local/proof-rail/aggregates/{aggregate_id} endpoint exists."""
        response = api_client.get("/api/local/proof-rail/aggregates/scenario_123")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_proof_rail_response_structure(self, api_client: TestClient):
        """Proof Rail API responses have correct structure."""
        response = api_client.get("/api/local/proof-rail")
        assert response.status_code == 200
        
        events = response.json()
        if len(events) > 0:
            event = events[0]
            assert "event_id" in event
            assert "event_type" in event
            assert "source" in event
            assert "severity" in event
            assert "summary" in event
            assert "created_at" in event
    
    def test_proof_rail_limit_parameter(self, api_client: TestClient):
        """Limit parameter restricts number of results."""
        response = api_client.get("/api/local/proof-rail?limit=10")
        assert response.status_code == 200
        
        events = response.json()
        assert len(events) <= 10


# =============================================================================
# Proof Rail Integration Tests
# =============================================================================

class TestProofRailIntegration:
    """Integration tests for Proof Rail with Cost Ledger."""
    
    def test_cost_receipt_events_in_proof_rail(self, proof_rail: ProofRail, calculator: CostCalculator):
        """Cost receipt generation creates proof rail events."""
        # Create scenario and receipt
        scenario = calculator.create_scenario(display_name="Integration Test")
        calculator.add_line_item(
            scenario_id=scenario.scenario_id,
            provider_kind=VendorProviderKind.RAILWAY,
            category="hosting",
            description="Test",
            quantity=Decimal("1"),
            unit_price_usd=Decimal("5.00"),
            frequency=CostFrequency.MONTHLY,
        )
        receipt = calculator.generate_receipt(
            scenario_id=scenario.scenario_id,
            display_name="Integration Receipt",
        )
        
        events = proof_rail.get_all_events()
        
        # Should have events for scenario and receipt
        scenario_events = [e for e in events if e.aggregate_id == scenario.scenario_id]
        assert len(scenario_events) >= 1
        
        receipt_events = [e for e in scenario_events if e.receipt_ref == receipt.receipt_id]
        assert len(receipt_events) >= 1
    
    def test_proof_rail_handles_no_events_gracefully(self, proof_rail: ProofRail):
        """Proof Rail handles empty state gracefully."""
        # Even with no data, should not raise errors
        events = proof_rail.get_all_events()
        assert isinstance(events, list)
        
        filtered = proof_rail.get_events_by_source("nonexistent")
        assert isinstance(filtered, list)
        
        filtered = proof_rail.get_events_by_type("nonexistent")
        assert isinstance(filtered, list)
        
        filtered = proof_rail.get_events_by_aggregate("nonexistent")
        assert isinstance(filtered, list)
    
    def test_proof_rail_events_have_required_fields(self, proof_rail: ProofRail, calculator: CostCalculator):
        """All Proof Rail events have required fields."""
        # Create some data
        calculator.create_scenario(display_name="Test")
        
        events = proof_rail.get_all_events()
        cost_events = [e for e in events if e.source == "cost_ledger"]
        
        for event in cost_events:
            # Required fields
            assert event.event_id is not None
            assert event.event_type is not None
            assert event.source is not None
            assert event.created_at is not None
            
            # Types
            assert isinstance(event.event_id, str)
            assert isinstance(event.event_type, str)
            assert isinstance(event.source, str)
            assert isinstance(event.created_at, datetime)
