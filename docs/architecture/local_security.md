# Local Secure Unlock Architecture

This document describes the security model for gating access to sensitive data within the Intake Local Console.

## Security Goal

Prevent unauthorized access to decrypted client data (location, access notes, etc.) and signing operations on the operator's local machine, even if the machine is left unlocked or the Local Console UI is compromised.

## Components

### 1. Swift SecureUnlockService (Native)

The primary authority for user presence. It leverages macOS `LocalAuthentication` to perform biometric (Touch ID) or passcode verification.

- **Technology**: `LAContext` with `.deviceOwnerAuthentication`.
- **Policy**: Verification is required to "open" a local authorization window.
- **Scope**: Native-only. Biometric data never leaves the macOS kernel and is never sent to the backend.

### 2. LocalAuthorizationWindow (Backend)

An in-memory service on the FastAPI backend that tracks the state of the secure unlock.

- **State**: Ephemeral (in-memory only).
- **TTL**: 120 seconds (configurable via `INTAKE_LOCAL_UNLOCK_TTL_SECONDS`).
- **Redaction**: When the window is closed (locked), sensitive fields in the `LocalDecryptedQuoteReview` model are returned as `null` or `[LOCKED]`.

### 3. KeychainSecretStore (Future Hardening)

A scaffold for binding the local authority to a cryptographic secret.

- **Goal**: Store a signing/decryption key in the macOS Keychain with `SecAccessControl` requiring biometrics for every usage.
- **Current Status**: Scaffolded. The system currently relies on the `LocalAuthorizationWindow` UI gate.

## Data Flow

1. **Discovery**: Operator views a list of quotes (redacted metadata only).
2. **Review Request**: Operator clicks "Review".
3. **Redacted Load**: Web UI fetches `/api/local/quotes/{id}/review`. If locked, it displays an "Unlock Required" overlay.
4. **Native Unlock**: Operator clicks "Unlock with Touch ID".
5. **Swift Verification**: `SecureUnlockService` triggers the macOS system dialog.
6. **Backend Refresh**: Upon success, the Swift shell calls `POST /api/local/security/unlock`.
7. **Decrypted Load**: Web UI reloads the quote. The backend now includes decrypted fields in the response.
8. **Expiry**: After 120s of inactivity, the window closes. Subsequent requests return redacted data.

## Security Boundaries

| Component | Responsibility | Threat Mitigated |
|-----------|----------------|------------------|
| Native Shell | Biometric Verification | Unauthorized operator presence |
| FastAPI Backend | In-memory Lock State | UI-only bypass |
| Keychain (Future) | Hardware-bound Key | Persistent secret theft |

## Hardening Path

- [x] Native biometric bridge
- [x] In-memory auth window
- [x] Server-side redaction logic
- [x] Manual "Lock Now" capability
- [x] E2E Dogfood Verification
- [ ] Cryptographic binding to Keychain-protected key
- [ ] Session binding between Swift shell and FastAPI via shared secret
