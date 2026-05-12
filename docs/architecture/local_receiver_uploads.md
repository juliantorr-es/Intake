# Local Receiver Uploads Architecture

## Overview

Intake's Local Upload Receiver is a **loopback-only** component that handles direct client uploads to a local Intake instance. It is **separate from the Local Console** and operates as an independent service bound to `127.0.0.1`.

## Product Behavior

### Routing Decision Flow

When a client submits files with a quote, the hosted Intake service makes a routing decision:

```
Client Upload Request
         |
         v
+------------------+
|  Handshake with   |
|  Local Receiver   |
+------------------+
         |
    +----+----+------+
    |                 |
    v                 v
+-----------+   +--------------+
|  Online   |   |   Offline    |
+-----------+   +--------------+
    |                 |
    v                 v
+-----------+   +--------------+   +------------------+
|  Route to  |   |  Fallback    |   |  No Fallback     |
|  Local    |   |  Provider?   |--->|  Available       |
|  Receiver |   +--------------+   +------------------+
+-----------+         |                    |
                     v                    v
              +--------------+       +------------------+
              |  Route to     |       |  Quote Without    |
              |  Fallback    |       |  Files / Retry    |
              |  Provider    |       |  Later           |
              +--------------+       +------------------+
```

### Current Implementation (v0)

This slice implements:
- **Local receiver handshake** - Simple challenge/response to verify receiver is online
- **Upload session acceptance** - Session creation with validation
- **Multipart file ingest** - Standard HTTP multipart upload
- **Local filesystem storage** - Files stored under `.build/intake/local_receiver/uploads/`
- **Upload-complete receipt** - Generation of completion receipts with SHA256 hashes

## Boundaries

### Local Receiver is NOT the Local Console

The Local Receiver has **strictly defined responsibilities**:

**Allowed:**
- Health checks
- Handshake protocol
- Upload session creation/acceptance
- Multipart file ingest
- Local file receipt generation
- Completion receipt generation

**Forbidden:**
- Decrypted quote review
- Local settings management
- File browsing
- Arbitrary download
- Quote mutation/writeback
- Signing key export
- Decrypt key export
- Local Console dashboard APIs
- Provider token display

## Configuration

### Storage Path

- **Root**: `.build/intake/local_receiver/uploads/`
- **Partitioning**: Files are partitioned by upload session ID
- **Naming**: Server-generated unguessable file IDs (hex(16 bytes) = 32 chars)
- **Extensions**: Validated extension appended after allowlist check
- **Security**: Original filenames are **never** used in storage paths

### File Policy (v0)

**Allowed Content Types:**
- Images: `image/jpeg`, `image/png`, `image/webp`, `image/heic`
- Video: `video/mp4`, `video/quicktime`
- Documents: `application/pdf`

**Allowed Extensions:**
- `.jpg`, `.jpeg`, `.png`, `.webp`, `.heic`
- `.mp4`, `.mov`
- `.pdf`

**Default Limits:**
- Max single file: 150 MB
- Max files per session: 20
- Max total bytes per session: 500 MB
- Session expiry: 30 minutes

### Bind Address

- **Loopback-only**: Receiver binds to `127.0.0.1` only
- **Port**: 8001 (default for receiver API)
- **Non-loopback binding is rejected or normalized to loopback**

## API Endpoints

All endpoints are under the `/receiver` prefix:

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/receiver/health` | Returns receiver availability status |
| POST | `/receiver/handshake` | Performs handshake, returns capabilities |
| POST | `/receiver/uploads/session` | Creates a new upload session |
| GET | `/receiver/uploads/session/{session_id}` | Gets upload session info |
| POST | `/receiver/uploads/{session_id}/file` | Uploads a file (multipart) |
| POST | `/receiver/uploads/{session_id}/file/stream` | Uploads a file (streaming, experimental) |
| POST | `/receiver/uploads/{session_id}/complete` | Marks session as complete |
| GET | `/receiver/uploads/{session_id}/receipt` | Gets completion receipt |

### Example Flow

```bash
# 1. Handshake
curl -X POST http://127.0.0.1:8001/receiver/handshake

# 2. Create session
curl -X POST http://127.0.0.1:8001/receiver/uploads/session \
  -H "Content-Type: application/json" \
  -d '{"quote_id": "quote_abc123", "expires_at": "2024-12-01T00:00:00Z"}'

# 3. Upload file
curl -X POST http://127.0.0.1:8001/receiver/uploads/{session_id}/file \
  -F "file=@photo.jpg" \
  -F "declared_content_type=image/jpeg" \
  -F "original_filename=photo.jpg"

# 4. Complete session
curl -X POST http://127.0.0.1:8001/receiver/uploads/{session_id}/complete \
  -H "Content-Type: application/json" \
  -d '{"session_id": "{session_id}", "quote_id": "quote_abc123"}'
```

## Security Considerations

### No Secrets in Responses

- Handshake responses contain **no credentials, tokens, or keys**
- No filesystem paths are exposed in public responses
- `local_url` is only included when in local-dev mode

### No Path Traversal

- Session IDs are sanitized before directory creation
- Original filenames are **never** used in storage paths
- All storage paths are validated to remain under the upload root
- Generated file IDs are cryptographically random (secrets.token_hex)

### File Validation

All uploads are validated:
- ✅ Session exists and is active
- ✅ File is not empty
- ✅ File size within limits
- ✅ Content type is allowed
- ✅ Extension is allowed
- ✅ Extension matches declared content type
- ✅ Session limits not exceeded (file count, total bytes)
- ✅ Session not expired
- ✅ Session not already completed

## Known Gaps

This is **v0** of the Local Receiver. The following are explicitly **not implemented**:

- **Public tunnel integration** - Tailscale Funnel and Cloudflare Tunnel are future features
- **Resumable uploads** - tus protocol is a future candidate
- **Object storage** - Cloud storage fallback is a future feature
- **Large file streaming** - v0 loads files into memory for validation
- **Atomic file writes** - v0 uses temp-file + rename, but full atomicity is not guaranteed on all platforms
- **File encryption at rest** - Files are stored unencrypted on local filesystem
- **Public URL exposure** - Receiver is loopback-only in this slice
- **GUI/file picker** - No frontend components for file selection
- **Download/delivery** - No download endpoints from receiver

## Future Work

### Next Recommended Slices

1. **Tunnel Adapter Layer** - Add Tailscale Funnel / Cloudflare Tunnel support
2. **Resumable Upload v0** - Add tus protocol support for resumable uploads
3. **Fallback Provider Integration** - Integrate with hosted fallback storage
4. **Streaming Upload Improvements** - Full streaming without memory limits
5. **Atomic Write Guarantees** - Platform-specific atomic write implementations

### Migration Path

```
Current: Local Loopback Only (127.0.0.1)
  |
  v
Future: + Tailscale Funnel (HTTPS tunnel to local)
  |
  v
Future: + Cloudflare Tunnel (HTTPS tunnel to local)
  |
  v
Future: + Object Storage Fallback (S3/R2/etc.)
```

## References

- [Provider Architecture](./provider-architecture.md) - Open upload/provider architecture
- [Upload Routing](./upload-routing.md) - Upload routing decision logic
- [Provider Boundary Proof](./provider_boundary.md) - Architecture boundary proofs
