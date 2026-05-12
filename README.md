# Intake

Passkey-gated, locally decryptable client intake platform for a freelance services website.

Intake follows a split-brain architecture designed for maximum security and operational reliability:

- **Hosted Intake (Public)**: A hosted web backend serving the public website and API. It handles passkey authentication, email verification, quote submission (encrypted shells), and binary uploads. It is designed to be "boring, available, and public."
- **Local Intake Console (Local)**: A private management app for operators. It connects outbound to the hosted backend, holds the private decryption keys, and manages site content, quote reviews, and service configurations.
- **Local Upload Receiver**: A loopback-only service for direct client file uploads. Separate from the Local Console, it handles multipart uploads, session management, and local file storage. Currently bound to `127.0.0.1` only.
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
│   ├── hosted/             # Hosted Public Backend module
│   │   ├── api/            # API routers
│   │   ├── auth/           # Passkey and account logic
│   │   ├── quotes/         # Quote intake logic
│   │   └── uploads/        # Binary upload logic
│   ├── deploy/             # Host Bootstrapping & Deployment module
│   │   ├── adapters/       # Provider-specific adapters (Railway, etc.)
│   │   ├── tunnel_adapters/# Tunnel dry-run adapters (Tailscale, Cloudflare)
│   │   │   ├── models.py   # Tunnel adapter models
│   │   │   ├── service.py  # Tunnel adapter service
│   │   │   ├── tailscale_funnel.py  # Tailscale adapter
│   │   │   ├── cloudflare_tunnel.py # Cloudflare adapter
│   │   │   └── __init__.py
│   │   ├── models.py       # Deployment domain models
│   │   └── registry.py     # Provider registry
│   ├── local_console/      # Local Management Console module
│   │   └── receiver/       # Local Upload Receiver (separate from console)
│   ├── sync/               # Sync protocol models
│   ├── domain/             # Pure domain models (Pure Python)
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
│   ├── test_passkey_shapes.py
│   ├── test_local_receiver.py      # Local Upload Receiver tests
│   ├── test_tunnel_adapters.py      # Tunnel adapter tests
│   ├── test_provider_routing.py     # Provider routing tests
│   └── test_railway_dry_run.py       # Railway dry-run tests
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

#### CryptoService Integration
Sensitive quote payloads are encrypted using the project's `CryptoService` (AES-GCM):
- **Exact Location**: Encrypted at rest.
- **Access Notes**: Encrypted at rest.
- **Questionnaire**: Encrypted at rest.
- **Original Filenames**: Encrypted at rest in upload metadata.
- Public APIs only return "saved" or "stored" statuses for these fields.

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

## Local Intake Console

The Local Intake Console is a native-looking application (powered by `pywebview`) for operators to review and decrypt client data locally.

### Running the Console

1. **Install dependencies**:
   ```bash
   pip install -e ".[console]"
   ```

2. **Run the console**:
   ```bash
   export PYTHONPATH=$PYTHONPATH:$(pwd)/src
   python -m intake.local_console.app
   ```

3. **Diagnostic CLI** (Legacy/Development only):
   ```bash
   python -m intake.local_console.dev_cli --help
   ```

## Hosted/Local Boundary

Intake enforces a strict data boundary:
- **Hosted Backend**: Serves public requests, stores ciphertext, lacks decryption authority.
- **Local Console**: Pulls data outbound, decrypts locally using private keys.
- **Sync Protocol**: Secure outbound polling mechanism for data projection.

See [Hosted/Local Boundary](docs/architecture/hosted-local-boundary.md) for full architecture details.

## Host Bootstrapping

Intake includes a **Deployment Adapter Architecture** to help operators provision and configure Hosted Intake instances.
- **Provider Adapters**: Currently supports **Railway** artifact generation.
- **Security First**: Local private keys are NEVER included in deployment artifacts.
- **Artifact Generation**: Generates `railway.json` and `.env.hosted.example` for manual or CLI-based deployment.

See [Host Bootstrapping](docs/architecture/host-bootstrapping.md) for full details.

### Railway Dry-Run Bootstrap - ✅ IMPLEMENTED

**Status**: This slice is now implemented with full dry-run capability.

The Railway dry-run bootstrap service provides:
- **CLI Detection**: Checks `railway --version`, `which railway`, `command -v railway`
- **Auth Detection**: Scans for Railway config files (non-mutating, no API calls)
- **Project Detection**: Checks for `railway.json` in working directory
- **Dry-Run Plan Generation**: Returns complete deployment plan as text without executing anything
- **Artifact Validation**: Validates that no forbidden env vars leak into generated artifacts

**Key Safety Guarantees**:
- ✅ No Railway API calls (no `railway login status`, no `railway projects`)
- ✅ No mutating commands executed (`railway init`, `railway link`, `railway up` never run)
- ✅ Commands returned as text strings only
- ✅ Local-only env vars (INTAKE_LOCAL_SIGNING_KEY, etc.) NEVER included in deployment plans
- ✅ Forbidden keys only appear in comments in generated `.env.hosted.example`

**Local Console API Endpoints**:
- `GET /deploy/status` - Deployment readiness status
- `GET /deploy/railway/dry-run` - Generate Railway dry-run plan

**Usage**:
```python
from intake.deploy.railway_dry_run import RailwayDryRunBootstrapService

service = RailwayDryRunBootstrapService()
plan = service.build_dry_run_plan(app_name="my-intake")

# Review what would happen without executing
print(f"CLI present: {plan.railway_cli_present}")
print(f"Blocking issues: {plan.blocking_issues}")
print("Commands that would run (text only):")
for cmd in plan.commands_that_would_run:
    print(f"  {cmd}")
```

## Provider Architecture

Intake implements an **open upload/provider architecture** with local-first routing:

### Upload Route Priority
1. **Local Receiver** (127.0.0.1) - Direct upload, zero latency
2. **Fallback Provider** - Cloud storage buffer when local is offline
3. **Quote Without Files** - Submit metadata only when all providers unavailable

### Provider Categories

**Hosted Backend Providers** (for Intake backend hosting):
- **Railway** - First-class target, full dry-run support implemented
- Render - Stub adapter
- Fly.io - Stub adapter
- Docker VPS - Future

**Upload Receiver Providers** (expose local receiver publicly):
- **Local Loopback** - Development, implemented
- Tailscale Funnel - Planned (candidate for secure direct device access)
- Cloudflare Tunnel - Planned (candidate for custom domain exposure)

**Fallback Storage Providers** (buffer files when local offline):
- Google Drive - Planned (fallback object provider, NOT canonical database)
- S3 Compatible - Planned
- Cloudflare R2 - Planned
- iCloud CloudKit - Experimental

**Resumable Upload Protocol**:
- **tus Protocol** - Planned (open standard, HTTP-based, Uppy integration)

See [Provider Architecture](docs/architecture/provider-architecture.md) for full details.

### Why Google Drive is Fallback Only

Google Drive is explicitly a **fallback object/file provider, not the canonical database**:
- It's object storage, not a structured database
- Cannot replace PostgreSQL/SQLite for Intake's relational data
- Drive API has rate limits and pagination
- Search is limited compared to SQL queries needed for quote management
- The **hosted backend remains the control plane** for routing, auth, and sync coordination
- Google Drive would only be used as a dumb file buffer

### Why tus/Uppy for Resumable Uploads

[tus](https://tus.io/) is an open protocol for resumable file uploads:
- **Resume capability**: If tab closes or network drops, uploads resume
- **HTTP-based**: Works through proxies, firewalls
- **Uppy integration**: [Uppy](https://uppy.io/) has first-class tus support
- **Features**: Automatic retry, parallel uploads, progress tracking, chunked uploads
- **Fit**: Works perfectly with Intake's "local receiver first, fallback later" model

See [Upload Routing Architecture](docs/architecture/upload-routing.md) for full details.

### Why Tailscale Funnel & Cloudflare Tunnel

**Tailscale Funnel**:
- Creates public HTTPS endpoint for local service
- Funnel URLs: `https://<funnel-name>.ts.net`
- Zero-configuration TLS certificates
- Built-in authentication options
- Can expose `127.0.0.1:8000` directly
- **Strong candidate** for direct device uploads with minimal setup

**Cloudflare Tunnel**:
- `cloudflared` creates secure tunnels to localhost
- Supports custom domains (e.g., `upload.yourdomain.com`)
- Built-in DDoS protection and WAF
- **Strong candidate** for production custom-domain deployments

## Provider Boundary

The **Provider Boundary** ensures safe interaction with external providers:

- ✅ No direct provider API calls from public routes
- ✅ No credential exposure in public APIs, logs, or UI
- ✅ Provider secrets always redacted through multiple passes
- ✅ Filesystem paths Never exposed in public responses
- ✅ Explicit separation of hosted-safe vs local-only env vars
- ✅ Safe failure (provider errors don't crash app or expose secrets)
- ✅ Full auditability (all interactions logged without secrets)

See [Provider Boundary Proofs](docs/proofs/provider_boundary.md) for detailed proofs.

## Current Status

### ✅ Implemented in This Slice
- Railway dry-run bootstrap service (`src/intake/deploy/railway_dry_run.py`)
- Upload provider models (`src/intake/deploy/models_upload.py`)
  - `UploadProviderKind` enum (9 provider kinds)
  - `UploadProviderCapability` enum (9 capabilities)
  - `UploadRouteDecision`, `UploadFallbackPolicy`, `ReceiverHandshakeResult`
  - `ProviderConfigRedacted`, `ProviderHealthCheck`
- Provider config redaction utilities (`src/intake/deploy/provider_redaction.py`)
  - `redact_secret_value()` - Redacts secret-looking values
  - `redact_dict_keys()` - Redacts sensitive dict keys recursively
  - `redact_file_paths()` - Redacts filesystem paths
  - `sanitize_provider_config()` - Full sanitization pipeline
  - `get_redacted_fields()` - Lists redacted field paths
- Local Console API endpoints for deployment readiness
- Updated Railway adapter with dry-run integration
- Documentation:
  - [Provider Architecture](docs/architecture/provider-architecture.md)
  - [Upload Routing Architecture](docs/architecture/upload-routing.md)
  - [Provider Boundary Proofs](docs/proofs/provider_boundary.md)
  - [Host Bootstrapping (updated)](docs/architecture/host-bootstrapping.md)

### 📋 Tests Added
- `tests/test_railway_dry_run.py` - 20+ tests
- `tests/test_provider_routing.py` - 30+ tests
- `tests/test_upload_broker.py` - 24+ tests for hosted upload logic

### 📋 Future Work (NOT in this slice)
- Actual `railway up` execution
- Real Tailscale Funnel integration
- Real Cloudflare Tunnel integration
- Real Google Drive API calls
- Real S3/R2 API calls
- tus server implementation for resumable uploads
- Provider credential storage

## ✅ What This Slice DOES Include

- ✅ **Local Upload Receiver v0** - Full implementation with:
  - Receiver handshake endpoint `/receiver/handshake`
  - Health check endpoint `/receiver/health`
  - Upload session creation `/receiver/uploads/session`
  - Multipart file upload `/receiver/uploads/{session_id}/file`
  - Session completion `/receiver/uploads/{session_id}/complete`
  - Local filesystem storage under `.build/intake/local_receiver/uploads/`
  - SHA256 file verification and receipts
  - Loopback-only binding (127.0.0.1)
  - File validation (content type, extension, size, limits)
  - Route decision integration
  - Local Console status integration

- ✅ **Hosted Upload Session Broker** - Central policy authority for uploads:
  - Route selection logic (Local Receiver priority, Fallback buffer)
  - Secure upload session creation `/quotes/{id}/upload-route`
  - Validated receipt processing `/quotes/{id}/uploads/receipt`
  - Safe public summaries `/quotes/{id}/uploads`
  - Redacted client-safe responses (no local paths, no keys/tokens)
  - Quote-level ownership and status authorization
  - Verified email enforcement for upload sessions
  - SHA256 integrity verification across the boundary

- ✅ **Tunnel Adapter Dry-Run Scaffolding** - Dry-run only tunnel integration:
  - Tailscale Funnel adapter with read-only CLI detection
  - Cloudflare Tunnel adapter with read-only CLI detection
  - Text-only command generation (NEVER executed)
  - Exposure policy (loopback-only, console-never-exposed)
  - API endpoints: `/tunnel/status`, `/tunnel/{provider}/dry-run`

- ✅ **Documentation**:
  - [Local Receiver Uploads](docs/architecture/local_receiver_uploads.md)
  - [Tunnel Adapter Dry-Run Scaffolding](docs/architecture/tunnel_adapters.md)
  - Boundary proof: [Tunnel Adapter Boundary](docs/proofs/tunnel_adapter_boundary.md)

- ✅ **Tests**:
  - `tests/test_local_receiver.py` - 18 passing tests
  - `tests/test_tunnel_adapters.py` - 40 passing tests

## What This Slice Intentionally Does NOT Do

- ❌ Does NOT run `railway up`
- ❌ Does NOT run `fly deploy`
- ❌ Does NOT call Render APIs
- ❌ Does NOT call any provider APIs
- ❌ Does NOT create provider projects
- ❌ Does NOT store provider tokens
- ❌ Does NOT add real Google Drive OAuth
- ❌ Does NOT execute real Tailscale/Cloudflare tunnel commands
- ❌ Does NOT add payments
- ❌ Does NOT add calendar integration
- ❌ Does NOT add SMS
- ❌ Does NOT add object storage implementation
- ❌ Does NOT add inbound control channels
- ❌ Does NOT expose public URLs for receiver (tunnel commands are text-only)
- ❌ Does NOT implement resumable uploads (tus)

## Next Recommended Slice

**Client Upload UI Integration**: Wire the public client quote flow to the Hosted Upload Session Broker.

This will:
- Update the public quote page upload step
- Implement browser-side upload flow (request route -> upload to receiver -> complete session -> send receipt)
- Ensure safe DOM rendering and redacted status displays
- Maintain all security boundaries regarding keys, tokens, and paths

**Why this is next**: The Hosted Upload Session Broker and Local Receiver are now fully implemented and tested. The next step is to make this capability available to clients through the public web interface.
