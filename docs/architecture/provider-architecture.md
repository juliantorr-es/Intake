# Provider Architecture

Intake's open upload/provider architecture implements a local-first strategy with intelligent fallback routing. This document describes the architecture, routing priorities, and provider candidates.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Client Upload Flow                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────┐     ┌──────────────┐     ┌──────────────────┐   │
│  │  Client  │────▶│ Upload Router │────▶│ Local Receiver   │   │
│  └──────────┘     └──────────────┘     │  (127.0.0.1)      │   │
│                                      │  + Direct Upload   │   │
│                                      └──────────┬───────┘   │
│                                                 │           │
│                                      ┌──────────▼───────┐   │
│                                      │                    │   │
│                              No орта  │ Fallback Provider │   │
│                           or offline │   (Cloud Storage)  │   │
│                                      │   + Buffer Files   │   │
│                                      └──────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```
### Control Plane: Hosted Upload Session Broker
The **Hosted Upload Session Broker** acts as the control plane for all upload providers. It centralizes routing decisions, session issuance, and receipt validation, ensuring that clients follow the authoritative path chosen by the Hosted Intake backend.

## Upload Route Priority

Intake uses a strict priority order for upload routing:

### Priority 1: Local Receiver (if online and handshake succeeds)
- Client uploads directly to local Intake instance via loopback
- End-to-end encrypted uploads when possible
- Streaming uploads for large files without local storage limits
- **Current state**: `LOCAL_LOOPBACK_DEV` implemented

### Priority 2: Fallback Provider (if configured and primary fails)
- Cloud storage provider buffers files temporarily
- Files are processed when local receiver comes back online
- Sync protocol marks files for re-delivery
- **Planned providers**: Google Drive, S3-compatible, Cloudflare R2

### Priority 3: Quote Submission Without Files
- If both primary and fallback are unavailable
- Client can submit quote metadata without file attachments
- Files can be uploaded later via retry or manual process
- **Current state**: Supported by quote API

## Provider Categories

### Hosted Backend Providers

These providers host the Intake backend service (FastAPI application):

| Provider | Kind | Status | Notes |
|----------|------|--------|-------|
| Railway | `RAILWAY` | **First-class, implemented** | Nixpacks builder, easy GitHub deploy |
| Render | `RENDER` | Stub adapter | Blueprints available |
| Fly.io | `FLY_IO` | Stub adapter | Docker-based, CLI deploy |
| Docker VPS | `DOCKER_VPS` | Future | Self-hosted Docker |

**Railway is the primary target** because:
- Explicit FastAPI deployment guide with multiple methods (GitHub, CLI, Dockerfile, templates)
- `railway up` uploads and deploys current directory
- Generous free tier for development
- Nixpacks automatically handles Python dependencies

### Upload Receiver Providers

These providers expose the local Intake instance to receive direct uploads:

| Provider | Kind | Status | Use Case |
|----------|------|--------|----------|
| Local Loopback | `LOCAL_LOOPBACK_DEV` | **Implemented** | Development, same-device uploads |
| Tailscale Funnel | `TAILSCALE_FUNNEL_FUTURE` | Planned | Secure tunnel via Tailscale, direct device access |
| Cloudflare Tunnel | `CLOUDFLARE_TUNNEL_FUTURE` | Planned | Custom domain, HTTPS termination |

**Tailscale Funnel Analysis:**
- Creates a public HTTPS endpoint for your local service
- Funnel URLs format: `https://<funnel-name>.ts.net`
- Zero-configuration TLS certificates
- Built-in authentication options
- Can expose `127.0.0.1:8000` directly to the internet
- **Strong candidate** for direct device uploads with minimal setup

**Cloudflare Tunnel Analysis:**
- `cloudflared` creates secure tunnels to localhost
- Supports custom domains (e.g., `upload.yourdomain.com`)
- SGW (Service Gateway) routing
- Built-in DDoS protection and WAF
- **Strong candidate** for production custom-domain deployments

### Fallback Storage Providers

These providers store files temporarily when local receiver is unavailable:

| Provider | Kind | Status | Notes |
|----------|------|--------|-------|
| Google Drive | `GOOGLE_DRIVE_FALLBACK_FUTURE` | Planned | Ubiquitous, large free tier, familiar API |
| Hosted Buffer | `HOSTED_BUFFER_FUTURE` | Planned | Intake-hosted temporary storage |
| S3 Compatible | `S3_COMPATIBLE_FUTURE` | Planned | any S3-compatible endpoint |
| Cloudflare R2 | `CLOUDFLARE_R2_FUTURE` | Planned | S3-compatible, no egress fees |
| iCloud CloudKit | `CLOUDKIT_ICLOUD_EXPERIMENTAL` | Experimental | Apple ecosystem integration |

**Why Google Drive is a Fallback Only:**

Google Drive is explicitly a **fallback object/file provider, not the canonical database**:

1. **Not a database**: Google Drive is object storage, not a structured database. It cannot replace PostgreSQL/SQLite for Intake's relational data (quotes, users, sessions, sync state).

2. **pagination and limits**: Drive API has rate limits and pagination that complicate real-time query patterns.

3. **Search limitations**: Drive's search is limited compared to SQL queries needed for quote management.

4. **Metadata vs Content**: Intake's hosted backend needs SQL for complex queries on quote metadata. Google Drive can only store file content.

5. **The control plane stays hosted**: The hosted backend remains the control plane for routing decisions, authentication, authorization, and sync coordination. Google Drive would only be used as a dumb file buffer.

### Resumable Upload Protocol Providers

| Provider | Kind | Status | Notes |
|----------|------|--------|-------|
| tus Protocol | `TUS_RESUMABLE_FUTURE` | Planned | Open standard, HTTP-based |

**Why tus/Uppy for Resumable Uploads:**

[tus](https://tus.io/) is an open protocol for resumable file uploads built on HTTP:

1. **Resume capability**: If a tab closes or network drops, uploads resume from where they left off
2. **Create-Extend protocol**: Client creates upload, then extends it with chunks
3. **HTTP-based**: Works through proxies, firewalls, existing infrastructure
4. **Uppy integration**: [Uppy](https://uppy.io/) has first-class tus support via `@uppy/tus`

Uppy's tus integration features:
- Automatic retry on failure
- Resume after network interruption
- Parallel uploads (multiple files simultaneously)
- Progress tracking
- Chunked uploads for large files
- Compatible with any tus server implementation

This fits Intake's "local receiver first, fallback later" model perfectly:
- Client attempts tus upload to local receiver
- If local is offline, tus client can retry or switch to fallback endpoint
- Fallback provider can also implement tus protocol
- Same client code works for both routes

## Model Definitions

### UploadProviderKind

All planned provider kinds are explicitly enumerated to prevent typos and ensure type safety:

```python
# Local receiver
LOCAL_LOOPBACK_DEV = "local_loopback_dev"

# Tunnel providers
TAILSCALE_FUNNEL_FUTURE = "tailscale_funnel_future"
CLOUDFLARE_TUNNEL_FUTURE = "cloudflare_tunnel_future"

# Fallback storage
GOOGLE_DRIVE_FALLBACK_FUTURE = "google_drive_fallback_future"
HOSTED_BUFFER_FUTURE = "hosted_buffer_future"
S3_COMPATIBLE_FUTURE = "s3_compatible_future"
CLOUDFLARE_R2_FUTURE = "cloudflare_r2_future"
CLOUDKIT_ICLOUD_EXPERIMENTAL = "cloudkit_icloud_experimental"

# Resumable upload
TUS_RESUMABLE_FUTURE = "tus_resumable_future"
```

### UploadProviderCapability

Providers declare their capabilities to enable intelligent routing:

```python
DIRECT_UPLOAD       # Client can upload directly
RESUMABLE_UPLOAD    # Supports tus/resumable uploads
CHUNKED_UPLOAD      # Supports chunked uploads
STREAMING_UPLOAD    # Supports streaming uploads
LARGE_FILE          # Supports files > 100MB
CUSTOM_DOMAIN       # Supports custom domain exposure
END_TO_END_ENCRYPTION  # Supports E2EE
DEVICE_SYNC        # Supports sync across devices
WEBHOOK_NOTIFICATION # Supports upload completion webhooks
```

### UploadRouteDecision

The router decides where to send each upload:

```python
class UploadRouteDecision(BaseModel):
    chosen_provider: UploadProviderKind
    route_priority: int  # 1 = highest
    route_reason: str
    fallback_available: bool
    fallback_provider: Optional[UploadProviderKind]
    upload_endpoint: str
    upload_session: Optional[dict]  # Temp auth, not credentials
    expires_at: Optional[datetime]
```

### UploadFallbackPolicy

Configures fallback behavior (serializes without credentials):

```python
class UploadFallbackPolicy(BaseModel):
    primary_provider: UploadProviderKind
    fallback_providers: list[UploadProviderKind]
    max_retries: int = 3
    retry_delay_seconds: float = 2.0
    fallback_expiry_minutes: int = 60
    require_resumable_uploads: bool = False
    min_chunk_size_bytes: int = 5 * 1024 * 1024
    large_file_threshold_bytes: int = 100 * 1024 * 1024
```

## Security Boundaries

### Provider Configuration Redaction

All provider configurations MUST be redacted before exposure:

```python
# These are NEVER exposed in public APIs, logs, or UI:
- API keys / tokens
- Credentials / passwords
- Private keys
- Connection strings with passwords
- Filesystem paths
- Local-only keys (INTAKE_LOCAL_SIGNING_KEY, etc.)

# Public APIs may expose:
- Provider kind (e.g., "google_drive_fallback_future")
- Provider display name
- Provider capabilities
- Provider status (configured/connected/offline)
- Upload endpoint URL
- Temporary upload session tokens
```

### Upload Route Decision Redaction

Upload route decisions expose ONLY:
- The chosen upload endpoint URL
- Temporary session/tokens for this specific upload
- Expiry time for temporary credentials

They do NOT expose:
- Local filesystem paths
- Provider master credentials
- Any other provider secrets

### Local Console Visibility

The Local Console can see:
- Provider kind and display name
- Provider health/status
- Provider capabilities
- Non-sensitive metadata

It CANNOT see:
- Raw provider credentials
- Full configuration objects containing secrets
- Local filesystem paths in provider configs

## Implementation Status

| Component | Status | File |
|-----------|--------|------|
| Hosted Upload Session Broker | ✅ **Done** | `src/intake/hosted/api/upload_broker.py` |
| Provider kinds enum | ✅ **Done** | `src/intake/deploy/models_upload.py` |
| Provider capabilities enum | ✅ **Done** | `src/intake/deploy/models_upload.py` |
| Provider config redaction | ✅ **Done** | `src/intake/deploy/provider_redaction.py` |
| Route decision model | ✅ **Done** | `src/intake/deploy/models_upload.py` |
| Fallback policy model | ✅ **Done** | `src/intake/deploy/models_upload.py` |
| Local loopback provider | ✅ **Done** | Loopback is default |
| Railway dry-run | ✅ **Done** | `src/intake/deploy/railway_dry_run.py` |
| Tailscale Funnel | 📋 Future | Scaffold only |
| Cloudflare Tunnel | 📋 Future | Scaffold only |
| Google Drive | 📋 Future | Scaffold only |
| tus protocol | 📋 Future | Scaffold only |

## Next Steps

1. **Implement Local Receiver Handshake Scaffold** - First operational piece for direct uploads
2. **Implement tus server for local receiver** - Enable resumable uploads to local
3. **Implement Cloudflare Tunnel integration** - Custom domain exposure
4. **Implement Google Drive fallback** - Buffer storage
5. **Implement upload routing service** - Intelligent decision making
