"""Vendor Cost Ledger Module.

This module provides:
- Cost estimation models for vendors/providers
- Manual cost calculator service
- Timestamped cost receipt generation
- Source tracking and attribution

Key Design Principles:
- Every estimate must include assumptions
- Every provider fact must include source/captured_at or be marked manual
- Receipts must state pricing may change
- Provider costs must be separated from Intake license/support costs
- Secret/provider credentials must never appear in receipts
"""

from intake.costs.models import (
    # Enums
    CostCurrency,
    CostFrequency,
    CostTimeUnit,
    CostConfidence,
    CostRiskLevel,
    CostFactSourceKind,
    VendorProviderKind,
    # Models
    VendorProvider,
    VendorPricingFact,
    CostAssumption,
    CostSourceSnapshot,
    CostEstimateLineItem,
    CostEstimateScenario,
    VendorCostReceipt,
)
from intake.costs.calculator import CostCalculator, CostCalculatorError, get_cost_calculator

__all__ = [
    # Enums
    "CostCurrency",
    "CostFrequency",
    "CostTimeUnit",
    "CostConfidence",
    "CostRiskLevel",
    "CostFactSourceKind",
    "VendorProviderKind",
    # Models
    "VendorProvider",
    "VendorPricingFact",
    "CostAssumption",
    "CostSourceSnapshot",
    "CostEstimateLineItem",
    "CostEstimateScenario",
    "VendorCostReceipt",
    # Service
    "CostCalculator",
    "CostCalculatorError",
    "get_cost_calculator",
]
