# Intake

Passkey-gated, locally decryptable client intake platform for a freelance services website.

Intake follows a split-brain architecture designed for maximum security and operational reliability:

- **Hosted Intake (Public)**: A hosted web backend serving the public website and API. It handles passkey authentication, email verification, quote submission (encrypted shells), and binary uploads. It is designed to be "boring, available, and public."
- **Local Intake Console (Local)**: A private management app for operators. It connects outbound to the hosted backend, holds the private decryption keys, and manages site content, quote reviews, and service configurations.
- **Intake Sync**: The narrow protocol connecting them via outbound polling/WebSocket clients.

### Core Boundaries

- **No private keys in the public backend**: The hosted backend never holds the private decryption key.
- **Local-only decryption**: Sensitive data is only decrypted within the Local Intake Console.
- **Outbound-only sync**: The local console initiates all connections; the hosted backend never connects inbound to a local machine.
- **Diagnostic-only CLI**: Any CLI tools in the repository are for development and diagnostics only, not for product use.
- **No passwords**: Passkey-first authentication only.
- **Redacted public state**: Public APIs only expose non-sensitive summaries; full data is only available via the sync protocol to authenticated operator devices.

- No raw session tokens in storage
- No plaintext sensitive data in long-term database
- Encryption for readable sensitive data
- Hashing only for lookup/deduplication
- No innerHTML for user-controlled frontend content
- No eval or dynamic code execution
- No subprocess or Git commands from public backend

## Setup

```bash
# Clone and enter repo
cd Intake

# Create virtual environment (optional but recommended)
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Copy environment file
cp .env.example .env

# Edit .env and set INTAKE_DEV_ENCRYPTION_KEY
# Generate with: openssl rand -base64 32

# Initialize database
mkdir -p .build/intake
touch .build/intake/local.db

# Create initial migrations (if needed)
alembic revision --autogenerate -m "initial" 2>/dev/null || true
alembic upgrade head 2>/dev/null || true
```

## Development

```bash
# Start the dev server
./scripts/dev.sh

# Or directly:
uvicorn intake.app:app --reload --port 8000

# Open http://localhost:8000
```

## Tests

```bash
# Run all checks
./scripts/check.sh

# Or individually:
ruff check .
ruff format .
pytest
```

## Project Structure

```
Intake/
├── src/intake/
│   ├── app.py              # FastAPI application entry
│   ├── config.py           # Configuration management
│   ├── api/
│   │   ├── __init__.py
│   │   ├── health.py       # Health check endpoint
│   │   ├── auth_passkeys.py # Passkey authentication endpoints
│   │   └── quotes.py       # Quote intake endpoints
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── accounts.py     # Account domain models
│   │   ├── passkeys.py     # Passkey domain models
│   │   ├── quotes.py       # Quote domain models
│   │   ├── crypto.py       # Encryption primitives domain
│   │   ├── events.py       # Event sourcing models
│   │   └── projections.py  # Projection models for UI
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── db.py           # Database session management
│   │   ├── models.py       # SQLModel persistence models
│   │   └── repositories.py # Repository layer
│   ├── services/
│   │   ├── __init__.py
│   │   ├── passkey_service.py
│   │   ├── quote_service.py
│   │   ├── crypto_service.py
│   │   └── event_log.py
│   └── operator_console/
│       ├── __init__.py
│       ├── cli.py         # CLI entry point
│       └── decrypt.py     # Decryption utilities
├── tests/
│   ├── test_health.py
│   ├── test_crypto_service.py
│   ├── test_quote_models.py
│   ├── test_event_log.py
│   └── test_passkey_shapes.py
├── scripts/
│   ├── dev.sh              # Start dev server
│   └── check.sh            # Run linting and tests
└── web/
    └── static/
        ├── css/
        └── js/
    └── templates/
```

## Security Notes

### Encryption vs Hashing

- **Hashing** is used for lookup/deduplication only (challenges, credential IDs)
- **Encryption** is used for data that needs to be read later (quote payloads, exact locations)

### Production Key Management

Production key management is **intentionally not solved** in this bootstrap. The intended future architecture:

- Local private-key decryption for sensitive quote payloads
- Operator console unlocks with local private key
- No private keys in the public backend

### Current Limitations

This bootstrap uses a single development encryption key from the environment. In production:

- Use proper key management (HSM, KMS, or secure key vault)
- Implement key rotation
- Separate encryption keys per tenant/data type
- Never store private keys in the backend database

#### Local-Dev Mock Encryption
For the current slice, the **exact location** field uses mock encryption:
- Payload is accepted as `dev_encrypted_exact_location`.
- Storage is prefixed with `enc:` for visual verification in logs/DB.
- This is **plumbing only** and MUST be replaced by `CryptoService`-backed encryption using established library primitives before production use.
- Sensitive data is never returned in safe summary responses.

## Service Lanes

Quote intake supports these service lanes:

- `software_systems` - Custom software development
- `photography` - Photography services
- `practical_help` - Hands-on assistance
- `unsure` - Unsure of needs

## Quote Status Flow

```
draft -> submitted -> needs_review -> reviewing -> quoted -> accepted -> closed
                                   -> quoted -> declined -> closed
```

## Timezone Policy

All datetimes in Intake are **timezone-aware UTC** (`datetime(timezone.utc)`).

- Use `utc_now()` from `intake.domain.time` for current time
- Use `utc_expires_in(seconds)` for future expiry times
- Never use `datetime.utcnow()` (deprecated, returns naive datetime)
- All timestamps stored in the database are UTC
- All datetime comparisons are done with aware datetimes

This ensures consistent time handling across all components and avoids mixing naive and aware datetimes.

## Session Cookie Policy

Session cookies are configured centrally via environment variables:

| Setting | Default | Description |
|---------|---------|-------------|
| `INTAKE_SESSION_COOKIE_NAME` | `intake_session` | Cookie name |
| `INTAKE_SESSION_COOKIE_HTTPONLY` | `true` | Prevent JavaScript access |
| `INTAKE_SESSION_COOKIE_SAMESITE` | `lax` | CSRF protection level |
| `INTAKE_SESSION_TTL_SECONDS` | `86400` (24h) | Session lifetime |

### Local vs Production

- **Local development** (`INTAKE_ENV=local`): `Secure=false` is allowed for `http://localhost`
- **Production** (`INTAKE_ENV=production`): `Secure=true` is enforced, requiring HTTPS

Override by explicitly setting `INTAKE_SESSION_COOKIE_SECURE=true/false`.

### Security Properties

- **HttpOnly**: Always `true` - prevents XSS attacks from stealing cookies
- **SameSite**: `lax` by default - balances security and usability
- **Secure**: Auto-detected based on environment, or explicitly configured
- **Scope**: Session cookies reference session IDs only, never raw tokens

### Raw Token Handling

- Raw session tokens are **NEVER stored** in the database
- Only SHA-256 hash of the token is stored for lookup
- The raw token is returned to the client once via secure cookie
- Logout clears the cookie and revokes the session server-side

## Current Authentication Limitations

- Single-factor authentication only (passkey)
- No multi-factor authentication support
- No session refresh/rotation
- No concurrent session limits
- No IP-based session validation
- RP ID must be a domain string (use `localhost` for dev)

## Local Browser Passkey Testing

### Prerequisites

- Modern browser supporting WebAuthn (Chrome, Safari, Edge, Firefox)
- Local development server running on `http://localhost:8000`
- RP ID configured as `localhost` (not `127.0.0.1`)
- Origin configured as `http://localhost:8000`

### Test Flow

1. Start the dev server:
   ```bash
   ./scripts/dev.sh
   # or: uvicorn intake.app:app --reload --port 8000
   ```

2. Open http://localhost:8000/account in your browser

3. The **Local Dev Debug** panel shows:
   - RP ID and Origin configuration
   - WebAuthn support status
   - Session cookie status

4. **Registration**: Click "Create Passkey" button
   - Browser prompts for passkey creation (Touch ID / Windows Hello / Security Key)
   - On success: "Passkey created successfully!"
   - Page reloads showing signed-in state

5. **Login**: If signed out, click "Sign In with Passkey"
   - Browser prompts for passkey authentication
   - On success: "Signed in successfully!"
   - Session cookie is set

6. **Logout**: Click "Sign Out" button
   - Session is revoked server-side
   - Session cookie is cleared

### Supported Browsers

| Browser | Passkey Support | Notes |
|---------|----------------|-------|
| Chrome | ✅ Yes | Works on macOS, Windows, Android |
| Safari | ✅ Yes | Works on macOS, iOS (17+) |
| Edge | ✅ Yes | Works on Windows, macOS |
| Firefox | ✅ Yes | Works with security keys |

### Known Browser Caveats

- **Safari**: Requires macOS Ventura+ or iOS 17+. May not show passkey creation UI reliably on first attempt.
- **Firefox**: Typically requires a hardware security key for passkey support.
- **Chrome/Edge on Windows**: Uses Windows Hello if available.
- **Chrome/Edge on macOS**: Uses Touch ID if available.
- **IP addresses**: RP ID cannot be an IP address. Always use `localhost` for local dev.

### Production Configuration

For production deployment:
```bash
# Required settings
INTAKE_ENV=production
INTAKE_RP_ID=juliantorr.es
INTAKE_ORIGIN=https://juliantorr.es
INTAKE_SESSION_COOKIE_SECURE=true
```

## Current Authentication Limitations

- Single-factor authentication only (passkey)
- No multi-factor authentication support
- No session refresh/rotation
- No concurrent session limits per account
- No IP-based session validation
- No passkey backup/recovery flow
- RP ID must be a domain string (use `localhost` for dev)

## Next Recommended Slice

**Binary upload handling**: Secure upload of client-provided files with:
- Size limits and content type validation
- Server-side storage or object storage integration
- Encryption of uploaded files at rest
- Cleanup of expired/unreferenced uploads
