# Hosted/Local Product Boundary

Intake uses a "split-brain" architecture to ensure that sensitive client data is eventually inaccessible in plaintext on the public internet.

## The Hosted Backend (Public)
**Role**: Availability and Collection
- Serves the public website and API.
- Handles passkey authentication and session management.
- Performs email verification.
- Stores **ciphertext** and **redacted metadata** for quotes and uploads.
- **Current Dev State**: Holds the symmetric `INTAKE_DEV_ENCRYPTION_KEY` for convenience during bootstrap development.
- **Production Goal**: Hosted backend does not hold the private decrypt key (Local Console owns decryption authority).

## The Local Console (Private)
**Role**: Authority and Decryption
- Private application running on the operator's local machine.
- **Current Dev State**: Uses the same symmetric `INTAKE_DEV_ENCRYPTION_KEY` as the hosted backend.
- **Production Goal**: Holds the **private decryption keys** for asymmetric encryption (e.g., ECIES).
- Connects **outbound only** to the hosted backend via the Sync Protocol.
- Decrypts sensitive data (exact locations, questionnaire answers, original filenames) locally.

## The Sync Protocol
**Direction**: Bi-directional (Outbound Pull / Inbound Push)
- **Hosted-to-Local (Pull)**: The Local Console polls for new encrypted payloads.
- **Local-to-Hosted (Push)**: The Local Console pushes **Signed Local Device Actions** to mutate hosted state.
- **Redaction**: Hosted APIs only return shallow projections (`HostedQuoteProjection`) containing non-sensitive metadata (status, area, counts).
- **Encrypted Envelopes**: Sensitive data is wrapped in `EncryptedPayload` objects containing AES-GCM ciphertext.

## Signed Local Device Actions
To ensure that only authorized local devices can mutate hosted data, Intake uses asymmetric signatures.
- **Algorithm**: Ed25519 (Elliptic Curve Digital Signature Algorithm).
- **Mechanism**: Each Local Console generates a signing keypair. The public key is registered with the Hosted backend.
- **Envelopes**: Every mutation action is wrapped in a `LocalDeviceActionEnvelope` containing:
  - Canonicalized action payload.
  - Replay prevention (Unique `action_id`, `nonce`, and `issued_at` timestamp).
  - Cryptographic signature.
- **Verification**: The Hosted backend verifies the signature against the registered public key before executing any mutation.

## Data Security Properties (Dev Flow)
- **Encryption**: AES-GCM with 256-bit keys (symmetric).
- **Public Redaction**: Public status endpoints return redacted indicators rather than raw ciphertext.
- **Sync APIs**: Expose ciphertext only (EncryptedQuoteEnvelope), protecting against plaintext exposure on the wire.
- **Key Isolation**: In production, Hosted Intake will never have the authority to decrypt client payloads.
