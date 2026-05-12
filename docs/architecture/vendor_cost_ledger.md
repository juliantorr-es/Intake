# Vendor Cost Ledger Architecture

The **Vendor Cost Ledger** is a manual cost estimation system for Intake deployment planning. It provides transparent, auditability-first cost estimates for infrastructure services across multiple providers.

## Purpose

Infrastructure pricing is often opaque, and predatory SaaS pricing models can trap operators with hidden costs. The Vendor Cost Ledger makes cost assumptions **visible and auditible**, supporting Intake's anti-predatory-SaaS value proposition.

### Why This Matters

1. **Transparency**: Every estimate includes its assumptions, source URLs, and timestamps
2. **Auditability**: Source snapshots track where pricing data came from
3. **No Hidden Costs**: All provider costs are explicitly separated from Intake license/support costs
4. **Realistic Planning**: Estimates acknowledge that pricing may change

### Cloud Storage Pricing Example

Different providers have substantially different pricing models. For example:
- **Cloudflare R2**: Charges for storage and operation classes, with **no egress bandwidth fees** for any storage class
- **AWS S3**: Charges for storage, requests, and egress bandwidth

The Ledger captures these differences explicitly through assumptions and source-timestamped facts.

## Design Principles

1. **Manual Only**: No automatic web scraping, browser automation, or provider API calls
2. **Explicit Sources**: Every pricing fact includes a source URL or is marked as manual
3. **Timestamped**: Every source snapshot records when it was captured
4. **Disclaimed**: All receipts state "Pricing may change"
5. **Separated**: Provider costs are distinct from Intake license/support costs
6. **Redacted**: No provider credentials, tokens, or sensitive data in receipts

## Core Components

### Domain Models (`src/intake/costs/models.py`)

| Model | Purpose |
|-------|---------|
| `VendorProvider` | Provider metadata (name, URLs, category) |
| `VendorProviderKind` | Enum of supported providers |
| `VendorPricingFact` | A single pricing fact with source/captured_at |
| `CostAssumption` | Input used in calculations (e.g., "10GB storage") |
| `CostEstimateLineItem` | A cost line item (provider, amount, frequency) |
| `CostSourceSnapshot` | Metadata about where data came from |
| `CostEstimateScenario` | Container for line items and assumptions |
| `VendorCostReceipt` | Generated estimate with full audit trail |

### Enums

```python
# Provider kinds
VendorProviderKind:
  RAILWAY, RENDER, FLY, CLOUDFLARE_R2, GOOGLE_DRIVE,
  TAILSCALE, CLOUDFLARE_TUNNEL, SELF_HOSTED, CUSTOM

# Confidence levels
CostConfidence: VERIFIED, HIGH, MEDIUM, LOW, UNKNOWN

# Risk levels
CostRiskLevel: LOW, MEDIUM, HIGH, CRITICAL

# Source kinds
CostFactSourceKind: VENDOR_WEBSITE, THIRD_PARTY, MANUAL, API

# Frequencies
CostFrequency: ONE_TIME, MONTHLY, ANNUAL, USAGE_BASED
```

### Cost Calculator Service (`src/intake/costs/calculator.py`)

The `CostCalculator` service provides:

- **Provider Management**: List and retrieve vendor providers
- **Scenario Management**: Create, retrieve, update, delete, list scenarios
- **Line Item Management**: Add line items to scenarios with auto-calculation
- **Assumption Management**: Add, list, delete assumptions for scenarios
- **Fact Management**: Store and retrieve pricing facts
- **Snapshot Management**: Create source snapshots
- **Receipt Generation**: Generate cost receipts from scenarios

#### Key Methods

```python
# Scenario lifecycle
create_scenario(display_name, description, created_by, tags)
get_scenario(scenario_id)
update_scenario(scenario)
delete_scenario(scenario_id)
list_scenarios()

# Line items (auto-calculates totals)
add_line_item(scenario_id, provider_kind, category, description, quantity, 
             unit_price_usd, frequency, assumption_ids, fact_ids, snapshot_ids,
             confidence, risk_level, notes, sort_order)

# Assumptions
add_assumption(scenario_id, category, description, data_type, value, unit,
               confidence, risk_level, notes, source, source_url)
delete_assumption(scenario_id, assumption_id)

# Snapshots
add_snapshot(source_url, source_kind, vendor_kind, source_title, notes)

# Receipts
generate_receipt(scenario_id, display_name, description, valid_until_days,
                 disclaimer, created_by, client_id, quote_id)
list_receipts()
get_receipt(receipt_id)

# Provider lookup
list_providers()
get_provider(kind)
```

### Local Console API (`src/intake/local_console/api/costs.py`)

All endpoints are **local-only** (not exposed via hosted backend).

#### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/costs/providers` | List all vendor providers |
| GET | `/costs/scenarios` | List all scenarios |
| POST | `/costs/scenarios` | Create a new scenario |
| GET | `/costs/scenarios/{scenario_id}` | Get scenario with line items, assumptions, snapshots |
| POST | `/costs/scenarios/{scenario_id}/line-items` | Add line item to scenario |
| POST | `/costs/scenarios/{scenario_id}/assumptions` | Add assumption to scenario |
| POST | `/costs/snapshots` | Create a source snapshot |
| GET | `/costs/receipts` | List all receipts |
| POST | `/costs/receipts` | Generate a receipt from a scenario |

### Local Console UI (`src/intake/local_console/web/templates/costs.html`)

The UI follows the **"Local Glass + Workshop Ledger"** design language:

- **Warm Paper Surfaces**: White/off-white panels for content
- **Precise Cards**: Clean bordered cards for providers, scenarios, receipts
- **State Chips**: Color-coded badges for confidence, risk, status
- **Receipt-Style Line Items**: Monospaced fonts for IDs, timestamps, currency
- **Source Snapshot Cards**: Display source URL, kind, vendor, and captured_at

#### Color Semantics

| Color | Meaning | Usage |
|-------|---------|-------|
| Green (`--state-ok`) | Verified/healthy | High confidence, low risk |
| Blue (`--state-info`) | Information | Info badges, links |
| Amber (`--state-warn`) | Warning/needs review | Medium confidence, pricing caveats |
| Purple (`--state-private`) | Private/local-only | Unknown confidence, private data |
| Red (`--state-error`) | Error/danger | High risk, critical issues |

## Example: "Lean Intake Deployment" Scenario

This seeded example demonstrates a minimal Intake deployment:

**Line Items:**
- Railway instance (hobby tier): $0.00/month (free tier)
- Object storage: $0.00/month (included up to 1GB)
- Self-hosted fallback: $0.00/month (manual setup)
- Egress bandwidth: $0.00/month (included up to 5GB)

**Assumptions:**
- Storage needed: 10 GB
- Monthly bandwidth: 100 GB
- Instance count: 1

**Source Snapshots:**
- Railway pricing page (https://railway.app/pricing)

**Key Notes:**
- All costs show as $0.00 because they're within free tier limits
- Pricing notes explain the limits explicitly
- Source snapshot tracks where pricing was verified
- Every line item links to relevant assumptions

## Data Flow

```
┌─────────────────┐
│   Local Console  │
│    (Browser)     │
└────────┬────────┘
         │ GET /costs/providers
         ▼
┌─────────────────┐
│   API Router    │
│  (costs.py)     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  CostCalculator  │
│  (Service)       │──────┐
└────────┬────────┘      │
         │                │
    ┌────▼────┐    ┌──────▼──────┐
    │ Scenarios│    │   Receipts  │
    │ Line Items│    │  Snapshots  │
    │Assumptions│    │   Facts    │
    └──────────┘    └───────────┘
         │
         ▼
┌─────────────────┐
│  In-Memory      │
│  Storage        │
│  (dicts)        │
└─────────────────┘
```

## Security Boundaries

### Must Never Include

- Provider credentials or API tokens
- Private keys or signing keys
- Sync tokens or session tokens
- Local filesystem paths
- Decrypted quote payloads
- Raw ciphertext internals

### Must Always Include

- "Pricing may change" disclaimer on all receipts
- Source URLs for all pricing facts
- Timestamps for all source snapshots
- Confidence and risk levels for all estimates
- Separation between provider costs and Intake costs

## Integration Points

### With Quote Review
The Cost Ledger provides supporting evidence for quote cost estimates. Quote Review can reference scenario IDs and receipt IDs to show the cost breakdown.

### With Proof Rail
Cost receipts and snapshots can be referenced as proof events in the Proof Rail. For example:
- `proof_event.type = "cost_receipt_generated"`
- `proof_event.receipt_ref = receipt_id`
- `proof_event.aggregate_id = scenario_id`

This allows the Proof Rail to show cost estimation as part of the audit trail.

## Future Work

- Database persistence (currently in-memory)
- Cost comparison between scenarios
- Provider-specific templates
- Export to CSV/PDF
- Version history for scenarios
- Collaboration features (comments, approvals)
