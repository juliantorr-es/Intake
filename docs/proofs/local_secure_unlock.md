# Proof: Local Secure Unlock Redaction

This artifact demonstrates the redaction logic applied to sensitive quote data when the Local Console is in a locked state.

## 1. Locked State (Redacted)

When the `LocalAuthorizationWindow` is expired or manually locked, the `/api/local/quotes/{id}/review` endpoint returns masked values.

**Request:** `GET /api/local/quotes/quote_123/review` (Locked)

**Response:**
```json
{
  "quote_id": "quote_123",
  "status": "submitted",
  "is_decrypted": false,
  "is_locked": true,
  "exact_location": null,
  "access_notes": null,
  "questionnaire_answers": null,
  "upload_evidence": [
    {
      "file_id": "file-0",
      "original_filename": "[LOCKED]",
      "size_bytes": 0,
      "storage_provider": "locked"
    }
  ]
}
```

## 2. Unlocked State (Decrypted)

After a successful biometric verification, the fields are populated.

**Request:** `GET /api/local/quotes/quote_123/review` (Unlocked)

**Response:**
```json
{
  "quote_id": "quote_123",
  "status": "submitted",
  "is_decrypted": true,
  "is_locked": false,
  "exact_location": "123 Workshop Lane, Suite B",
  "access_notes": "Key is under the mat. Watch out for the dog.",
  "questionnaire_answers": {
    "site_access": "full",
    "power_available": true
  },
  "upload_evidence": [
    {
      "file_id": "file-0",
      "original_filename": "site_photo_1.jpg",
      "size_bytes": 1048576,
      "storage_provider": "local_loopback_dev"
    }
  ]
}
```

## 3. Automated Verification

Tests in `tests/test_local_security.py` verify this behavior programmatically:

```python
def test_quote_redaction_when_locked(auth_window):
    auth_window.lock()
    review = service.get_decrypted_review("quote_1")
    assert review.is_locked == True
    assert review.exact_location is None
    assert review.upload_evidence[0].original_filename == "[LOCKED]"
```

Status: **Verified**
- [x] Logic redaction implemented in `LocalQuoteReviewService`.
- [x] UI-gating implemented in `index.html` and `main.js`.
- [x] Biometric bridge implemented in Swift.
