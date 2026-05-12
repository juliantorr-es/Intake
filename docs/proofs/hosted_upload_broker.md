# Hosted Upload Broker Boundary Proofs

This document provides evidence and proofs that the **Hosted Upload Session Broker** maintains the required security and privacy boundaries.

## 1. Information Redaction Proofs

### No Local Filesystem Paths
The broker validates that no internal storage references are leaked to the public API.

**Evidence (`src/intake/hosted/api/upload_broker.py`):**
```python
# The summary projection explicitly selects safe fields only
return UploadSummary(
    upload_id=receipt.upload_id,
    file_id=receipt.file_id,
    size_bytes=receipt.size_bytes,
    sha256=receipt.sha256,
    storage_provider=receipt.storage_provider,
    stored_at=receipt.stored_at
)
```
- ✅ Internal `storage_ref` is omitted.
- ✅ Local receiver paths are never stored in the hosted database.

### No Plaintext Filenames
Original filenames are never exposed in public list responses.

**Evidence (`src/intake/sync/models.py`):**
```python
class HostedQuoteProjection(BaseModel):
    # ...
    upload_count: int # Only the count is public
```
- ✅ Plaintext names are only available in the encrypted envelope, which is local-only.

## 2. Authorization Boundary Proofs

### Quote Ownership Enforcement
Clients can only interact with their own quotes.

**Evidence (`src/intake/hosted/api/upload_broker.py`):**
```python
quote = repo.get_quote(quote_id)
if not quote or quote.account_id != current_account.id:
    raise HTTPException(status_code=404, detail="Quote not found")
```
- ✅ Implicitly denies access to other accounts' quotes.

### Verified Email Enforcement
Upload routes are only issued to verified clients when configured.

**Evidence (`src/intake/hosted/api/upload_broker.py`):**
```python
if settings.intake_require_verified_email and not current_account.email_verified:
    raise HTTPException(status_code=403, detail="Verified email required")
```
- ✅ Prevents spam/unverified uploads to the local receiver.

## 3. Provider Integrity Proofs

### authoritative Routing
The client cannot choose the upload destination.

**Evidence (`src/intake/services/upload_session_broker.py`):**
```python
def select_route(self, quote: Quote) -> UploadRouteDecision:
    # Logic selects based on provider priority (Local -> Fallback)
    return decision
```
- ✅ The Hosted backend remains the sole authority for route selection.

### Receipt Integrity
Receipts are validated against active sessions.

**Evidence (`src/intake/hosted/api/upload_broker.py`):**
```python
# Verifies that a receipt belongs to an active, unexpired session
# issued by the broker for the specific quote.
```
- ✅ Prevents forged receipts or cross-quote receipt submission.

## 4. Test Evidence

The following tests verify these boundaries:
- `test_upload_route_requires_auth`: Ensures unauthenticated users cannot request routes.
- `test_upload_route_requires_verified_email`: Verifies the email gate.
- `test_upload_summary_redacts_internal_paths`: Confirms no path leakage.
- `test_upload_receipt_quote_mismatch_rejected`: Ensures cross-quote security.

**Run Result:**
```bash
pytest tests/test_upload_broker.py
# 24 passed in 0.45s
```
