# Hosted/Local Product Boundary

Intake uses a "split-brain" architecture to ensure that sensitive client data is never accessible in plaintext on the public internet, even if the hosted backend is compromised.

## The Hosted Backend (Public)
**Role**: Availability and Collection
- Serves the public website and API.
- Handles passkey authentication and session management.
- Performs email verification.
- Stores **ciphertext** and **redacted metadata** for quotes and uploads.
- **Strict Rule**: Never holds the private decryption key for client data.

## The Local Console (Private)
**Role**: Authority and Decryption
- Private application running on the operator's local machine.
- Holds the **private decryption keys**.
- Connects **outbound only** to the hosted backend via the Sync Protocol.
- Decrypts sensitive data (exact locations, questionnaire answers, original filenames) locally.
- Manages service configurations and site content.

## The Sync Protocol
**Direction**: Outbound-only (Local -> Hosted)
- The Local Console polls or uses persistent outbound connections to fetch new encrypted payloads.
- **Redaction**: Hosted APIs only return shallow projections (`HostedQuoteProjection`) containing non-sensitive metadata (status, area, counts).
- **Encrypted Envelopes**: Sensitive data is wrapped in `EncryptedPayload` objects containing AES-GCM ciphertext, nonces, and tags.

## Data Security Properties
- **Encryption**: AES-GCM with 256-bit keys (Fernet/AES-CBC used for some bootstrap tokens).
- **No Mocking**: The `enc:` prefix system has been removed. All sensitive fields use the project `CryptoService`.
- **Public Redaction**: Public status endpoints return `saved` or `stored` indicators rather than raw ciphertext.
- **Key Isolation**: Production keys should be stored in HSM/KMS or local secure storage, never in the hosted database.
