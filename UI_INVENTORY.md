# UI Inventory - Intake Local Console

> Generated: UI Truthfulness Hardening Pass
> Status: BEFORE FIXES

## Legend
- **REAL**: Backed by real API endpoint with actual data
- **PARTIAL**: Real API but incomplete/misleading data
- **PLACEHOLDER**: Real structure but no real data flow
- **FAKE_STATIC**: Hardcoded static content pretending to be real
- **UNWIRED**: Element exists but no event handler or data binding
- **MISLABELLED**: Wrong name for what it actually does

---

## Swift Sidebar (ContentView.swift)

| UI Surface | Type | Current Reality | Problem | API Endpoint |
|------------|------|-----------------|---------|---------------|
| Inbox | NavSection | MISLABELLED | Maps to `/` (dashboard), no inbox model | - |
| Quotes | NavSection | PARTIAL | Uses local console quote projection | `/api/local/quotes/pending` |
| Uploads | NavSection | PLACEHOLDER | Standalone page, hardcoded static | `/uploads` |
| Deliveries | NavSection | MISLABELLED | Opens Cost Ledger at `/costs` | - |
| Deploy | NavSection | PARTIAL | Dry-run readiness only, misleading | `/api/local/deploy/status` |
| Providers | NavSection | MISLABELLED | Cost providers, not operational | `/api/local/costs/providers` |
| Settings | NavSection | PARTIAL | Wiring fragile, biometry unclear | `/settings` |

## Swift Status Chip (StatusChip)

| UI Surface | Type | Current Reality | Problem |
|------------|------|-----------------|---------|
| Backend health status | REAL | Reflects health client | Label should be "Local Backend" not general |

## Swift Proof Rail (ProofRailView)

| UI Surface | Type | Current Reality | Problem |
|------------|------|-----------------|---------|
| All proof items | FAKE_STATIC | Hardcoded events | No real API wiring |
| Local Decrypt | FAKE_STATIC | "Quote payload verified" | Never happened |
| Local Sync | FAKE_STATIC | "Pulled 3 projections" | Never happened |
| Payload Stored | FAKE_STATIC | "Encrypted envelope @ Hosted" | Never happened |
| Upload Received | FAKE_STATIC | "2 files @ Local Receiver" | Never happened |
| Quote Submitted | FAKE_STATIC | "Client session completed" | Never happened |
| Email Verified | FAKE_STATIC | "Client identity confirmed" | Never happened |
| Passkey Auth | FAKE_STATIC | "Device registration" | Never happened |
| Review Started | FAKE_STATIC | "Action placeholder" | Never happened |

**API Available:** `GET /api/local/proof-rail` - NOT CALLED

---

## HTML Sidebar (index.html)

| UI Surface | Type | Current Reality | Problem |
|------------|------|-----------------|---------|
| Dashboard | NavItem | REAL | Works |
| Cost Ledger | NavItem | REAL | Works |
| Quotes | NavItem | PARTIAL | Works but has demo seeding |
| Settings | NavItem | PARTIAL | JS fragile |
| Hosted: Online badge | Footer | FAKE_STATIC | Hardcoded |

## Dashboard View (index.html)

| UI Surface | Type | Current Reality | Problem |
|------------|------|-----------------|---------|
| Pending Quotes count | REAL | From `/api/local/quotes/pending` | Works |
| Security Level: Local-only | PARTIAL | True but too broad | Should be "Decryption: Local-only" |
| Hosted URL | REAL | From `/api/local/status` | Works |
| Sync Auth badge | REAL | From `/api/local/status` | Works |
| Encryption Key badge | PARTIAL | "Active" if configured | Should be "Configured" not "Active" |
| Signing Key badge | PARTIAL | "Active" if configured | Should be "Configured" not "Active" |
| Sync Now button | PARTIAL | Calls `/api/local/sync/pull` | Placeholder response, may not do real sync |

## Quotes View (index.html)

| UI Surface | Type | Current Reality | Problem |
|------------|------|-----------------|---------|
| Seed Demo Data button | FAKE_STATIC | Client-side only | Watermark needed |
| Quote rows (demo) | FAKE_STATIC | Pure JS objects | Reset on refresh |
| Review button (demo) | UNWIRED | Calls real API but demo IDs | Should be disabled for demo |
| Quote detail (demo) | FAKE_STATIC | Invented data | Location, notes, questionnaire |
| Upload evidence (demo) | FAKE_STATIC | Simulated placeholders | Content type, size, sha, storage |
| Start Review (demo) | UNWIRED | Would call real API | Should fail gracefully for demo IDs |

## Quote Detail View (index.html)

| UI Surface | Type | Current Reality | Problem |
|------------|------|-----------------|---------|
| Unlock overlay | REAL | Works with WK bridge | Depends on JS loading |
| Unlock timer | REAL | From `/api/local/security/status` | Works |
| Decrypted content | REAL | From `/api/local/quotes/{id}/review` | Works if not locked |
| Lock Now button | REAL | Calls `/api/local/security/lock` | Works |
| Start Review button | REAL | Calls `/api/local/quotes/{id}/start-review` | Works but fragile |

## Settings View (index.html)

| UI Surface | Type | Current Reality | Problem |
|------------|------|-----------------|---------|
| Local Secure Unlock badge | REAL | From `/api/local/status` | Works |
| Unlock Timeout (TTL) | REAL | From `/api/local/status` | Works |
| Test Local Secure Unlock button | PARTIAL | WK bridge or fallback | JS may fail silently |
| Workspace Root | UNWIRED | Always "..." | Never populated |
| Biometry labels | FAKE_STATIC | From `window.intakeBiometryType` | Not injected by Swift |

## Cost Ledger (costs.html)

| UI Surface | Type | Current Reality | Problem |
|------------|------|-----------------|---------|
| Side navigation | REAL | Links to /, /costs, quotes, settings | Works |
| Providers list | REAL | From `/api/local/costs/providers` | Works |
| Scenarios list | REAL | From `/api/local/costs/scenarios` | **JS TYPO: `;n` in loadScenarios** |
| Receipts list | REAL | From `/api/local/costs/receipts` | Works |
| New Scenario button | REAL | Creates scenario | Works |
| Load Example button | REAL | Seeds example data | Works |
| Pricing facts | PARTIAL | Manual vendor assumptions | Should be labeled "manual estimate" |

**CRITICAL: Line 319 in costs.html:**
```javascript
}).join('')
;n            }).join('')
```
The `;n` is a syntax error that will break the entire script.

## Uploads (uploads.html)

| UI Surface | Type | Current Reality | Problem |
|------------|------|-----------------|---------|
| Receiver Online badge | FAKE_STATIC | Hardcoded | No API call |
| Recent Local Uploads | FAKE_STATIC | Hardcoded empty | No API call |
| Port 8001 | FAKE_STATIC | Hardcoded | Not from config |
| Mode: Loopback-only | FAKE_STATIC | Hardcoded | Not from API |
| No script tag | UNWIRED | No JS at all | Can't fetch real data |

**API Available:** `GET /api/local/receiver/status` - NOT CALLED

## Providers (providers.html)

| UI Surface | Type | Current Reality | Problem |
|------------|------|-----------------|---------|
| Service Providers title | MISLABELLED | Shows cost providers | Should be "Cost Providers" or "Vendor Providers" |
| Providers list | REAL | From `/api/local/costs/providers` | Works |

## Deploy (deploy.html)

| UI Surface | Type | Current Reality | Problem |
|------------|------|-----------------|---------|
| Host Readiness section | PARTIAL | Real API | Should be labeled "Dry-Run Readiness" |
| Railway CLI status | REAL | From `/api/local/deploy/status` | Works |
| Project Linked | REAL | From `/api/local/deploy/status` | Works |
| Tailscale Funnel | PARTIAL | From API but oversimplified | No dry-run plan shown |
| Cloudflare Tunnel | PARTIAL | From API but oversimplified | No dry-run plan shown |
| Check Readiness button | REAL | Fetches status | Works |
| Labels | MISLABELLED | "Railway" as primary adapter | Should clarify dry-run only |

---

## External Dependencies

| UI Surface | Type | Current Reality | Problem |
|------------|------|-----------------|---------|
| Google Fonts (Inter, Outfit) | REAL | Loaded from CDN | Bad for local shell purity |

---

## Summary: Count by Type

- **REAL**: 28 surfaces
- **PARTIAL**: 16 surfaces  
- **PLACEHOLDER**: 3 surfaces
- **FAKE_STATIC**: 22 surfaces
- **UNWIRED**: 5 surfaces
- **MISLABELLED**: 4 surfaces

## Highest Priority Fixes

1. **Navigation Contract Drift** - Swift says 7 sections but HTML only knows 4
2. **Settings JS Fragility** - main.js failures kill all settings wiring
3. **Uploadsfake static** - No real API calls, hardcoded everything
4. **Proof Rail Lies** - Hardcoded events claiming real operations happened
5. **Cost Ledger JS Syntax Error** - `;n` breaks loadScenarios
6. **Quotes Demo Not Watermarked** - Fake data looks real
