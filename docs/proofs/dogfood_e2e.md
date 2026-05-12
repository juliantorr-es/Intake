# Dogfooding E2E Verification: Local Secure Unlock

**Date**: 2026-05-12
**Status**: VERIFIED
**Verdict**: READY for private dogfooding.

## Verification Summary

The end-to-end dogfooding loop for the Intake Local Console has been successfully verified. This verification proves that sensitive client data is correctly secured at rest on the hosted backend, synchronized to the local console, and gated behind macOS native biometrics (simulated via the backend authorization window).

### Key Workflows Verified

1.  **Hosted Submission**: Verified that clients can submit quotes with sensitive data (e.g., exact location) which is encrypted before storage.
2.  **Local Synchronization**: Verified that the Local Console can fetch non-sensitive projections of pending quotes from the hosted backend using a secure sync token.
3.  **Local Secure Unlock**:
    *   **Locked State**: Verified that sensitive fields are redacted when the Local Console's authorization window is locked.
    *   **Unlock Ceremony**: Verified that a successful unlock (simulated via the bridge) correctly enables local decryption.
    *   **Decrypted State**: Verified that sensitive fields (exact location) are correctly decrypted and displayed only when unlocked.
4.  **Signed Local Actions**: Verified that the Local Console can sign and push actions (e.g., `start-review`) to the hosted backend using hardware-bound (simulated) keys.

## Technical Evidence

### 1. Sync & Discovery
Pending quotes are correctly filtered and projected to the Local Console:
```json
[
  {
    "quote_id": "bf0afa86b4604c78addeb9528f8e065d",
    "status": "needs_review",
    "service_lane": "practical_help",
    "general_service_area": "Local Test Area"
  }
]
```

### 2. Redaction at Rest (Locked)
When the console is locked, sensitive fields are returned as `null`:
```json
{
  "quote_id": "bf0afa86b4604c78addeb9528f8e065d",
  "is_decrypted": false,
  "is_locked": true,
  "exact_location": null
}
```

### 3. Secure Decryption (Unlocked)
After a successful unlock, the Local Console performs client-side decryption:
```json
{
  "quote_id": "bf0afa86b4604c78addeb9528f8e065d",
  "is_decrypted": true,
  "is_locked": false,
  "exact_location": "123 Workshop Lane"
}
```

### 4. Transition Logic
Local device actions are verified by the hosted backend:
```json
{
  "action_id": "1ad489f8-0741-4f70-831b-252f011acf07",
  "aggregate_id": "bf0afa86b4604c78addeb9528f8e065d",
  "previous_status": "needs_review",
  "new_status": "reviewing"
}
```

## Readiness Verdict

The system is stable and the security boundaries are honest. The transition from "STARTUP_DASHBOARD" to "LOCAL_INSTRUMENT_PANEL" is functionally complete.

**Next Milestone**: Physical hardware verification of Touch ID performance.
