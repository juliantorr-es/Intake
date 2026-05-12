# Proof: Crypto Payload Boundary

This document verifies the technical controls ensuring that sensitive data is properly encrypted and redacted.

## Verified Sensitive Fields
The following fields are now secured using `CryptoService` (AES-GCM):
1. **Exact Location**: Stored as `EncryptedPayload`.
2. **Access Notes**: Stored as `EncryptedPayload`.
3. **Questionnaire Answers**: Stored as `EncryptedPayload`.
4. **Original Filenames**: Stored as `EncryptedPayload` in upload metadata.

## Redaction Enforcement
Automated tests (`tests/test_crypto_payload_boundary.py`) verify that:
- `Quote.get_safe_summary()` excludes all `encrypted_*` fields.
- Public API responses do not contain plaintext sensitive data or raw ciphertext internals.
- Summaries use status strings (e.g., `upload_count`, `general_service_area`) rather than detailed data.

## Encryption Proof
Tests confirm that:
- Decryption of `EncryptedPayload` objects using the `CryptoService` with the correct key recovers the original plaintext.
- The `enc:` prefix mock system is no longer present in the codebase.
- String encryption (`encrypt_string`) correctly wraps data in a JSON envelope `{"value": ...}` before encryption.

## Key Management (Dev Only)
In development, the `INTAKE_DEV_ENCRYPTION_KEY` is loaded from `.env` on both Hosted and Local environments.
- **Verification**: `tests/test_crypto_service.py` demonstrates that using the wrong key causes decryption to fail with a `ValueError`.
- **Limitation**: The current symmetric model does not yet provide cryptographic isolation between Hosted and Local; it provides data-at-rest protection and API-level redaction.

## Future: Key Authority Separation
Production will move to an asymmetric model:
1. **Hosted**: Holds public keys of registered Local Devices; encrypts payloads.
2. **Local**: Holds private keys; decrypts locally.
3. **Proof**: Future tests will verify that Hosted lacks the private key material entirely.
