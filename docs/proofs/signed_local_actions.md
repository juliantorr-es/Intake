# Proof: Signed Local Actions

This document verifies the technical controls for the Local Device signing authority.

## Technical Specification
- **Algorithm**: Ed25519
- **Serialization**: Canonical JSON (Sorted keys, no whitespace)
- **Replay Prevention**:
  1. `action_id`: Unique per action globally.
  2. `nonce`: Unique per device-action.
  3. `issued_at`: Must be within a 5-minute (300s) window of current server time.

## Verification Proofs
Automated tests in `tests/test_signed_actions.py` verify the following:

### 1. Integrity
Tampering with any part of the action envelope (payload, action_kind, nonce, etc.) results in a signature verification failure.

### 2. Authenticity
An action signed by a device other than the one registered (or with a different key) is rejected even if the device ID matches.

### 3. Replay Resistance
- **Action ID**: Re-submitting the exact same `action_id` is rejected.
- **Nonce**: Re-using a `nonce` for a specific device is rejected.
- **Timestamp**: Actions issued outside the freshness window (e.g., 10 minutes ago) are rejected to prevent delayed relay attacks.

## Implementation Details
- **Local Console**: Uses `LocalDeviceSigningService` to manage the private key and sign envelopes.
- **Hosted Backend**: Uses `HostedActionVerificationService` (scaffolded) to verify incoming envelopes against the registered `HostedRegisteredDevice.public_signing_key`.

## Security Caveat
During development, the `INTAKE_LOCAL_SYNC_TOKEN` still provides transport-level authentication. Device signatures provide the second layer of **intent-level authorization**.
