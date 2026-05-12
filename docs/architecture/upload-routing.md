# Upload Routing Architecture

This document describes how Intake routes client uploads based on provider availability, the decision-making process, and the rules governing route selection.

## Routing Decision Matrix

```
┌──────────────────────────────────────────────────────────────────────┐
│                    UPLOAD ROUTING DECISION MATRIX                     │
├──────────────────┬──────────────────┬──────────────────┬────────────┤
│ Local Status       │   Online         │     Offline       │ Overloaded │
├──────────────────┼──────────────────┼──────────────────┼────────────┤
│ Handshake Result   │ Success          │ Failure/Timeout   │ N/A        │
├──────────────────┼──────────────────┼──────────────────┼────────────┤
│ Primary Route     │ LOCAL_LOOPBACK  │ Fallback Provider │ Fallback   │
│ Fallback Route    │ (none)           │ GOOGLE_DRIVE      │ Provider   │
│ Decision Priority │ 1 (highest)      │ 2                 │ 2          │
└──────────────────┴──────────────────┴──────────────────┴────────────┘
```

## Priority Order

The upload router evaluates providers in this exact order:

### Priority 1: Local Receiver (direct)
**Route**: Client → Local Intake Instance (127.0.0.1)

**Conditions (all must be true):**
1. Local receiver is running (console app is active)
2. Handshake with local receiver succeeds
3. Local receiver has capacity (not overloaded)
4. Network connectivity between client and local instance exists

**Provider Kind**: `LOCAL_LOOPBACK_DEV`

**Protocol**: 
- HTTP POST to `/upload` endpoint on local console
- Streaming upload for large files
- Chunked upload for resumable transfers (future: tus)

**Advantages:**
- Zero latency (loopback interface)
- No egress costs
- Full control over data
- Immediate file processing
- Supports E2EE (local encryption keys available)

---

### Priority 2: Fallback Provider (buffered)
**Route**: Client → Fallback Storage Provider → Local Receiver (when back online)

**Conditions:**
- Priority 1 failed OR local receiver is offline
- Fallback provider is configured
- Fallback provider is Healthy

**Provider Kinds (prioritized):**
1. `HOSTED_BUFFER_FUTURE` - Intake's own hosted buffer
2. `CLOUDFLARE_R2_FUTURE` - Cloudflare R2 storage
3. `S3_COMPATIBLE_FUTURE` - Any S3-compatible storage
4. `GOOGLE_DRIVE_FALLBACK_FUTURE` - Google Drive buffer

**Sync Behavior:**
- File is bufferred in fallback storage
- Local receiver polls or receives webhook when online
- File is downloaded to local storage
- Sync protocol marks file as "retrieved"
- Fallback storage deletes file after confirmation

**Client Experience:**
- Upload succeeds to fallback (immediate confirmation)
- Client is notified: "File buffered, will sync when local is back online"
- Client can see sync status in UI

---

### Priority 3: Quote Without Files
**Route**: Client Upload Endpoint → Hosted Backend (metadata only)

**Conditions:**
- Both Priority 1 and Priority 2 are unavailable
- Client has quote metadata to submit

**Behavior:**
- Client submits quote with empty file list
- Hosted backend creates quote with `files_pending` flag
- When local comes back online, client is prompted to retry file upload
- Alternative: Client can manually upload files later

**Use Cases:**
- Critical quote submission deadline
- Poor network conditions
- All storage providers offline

## Route Decision Model

The **Hosted Upload Session Broker** is the authoritative source for upload routes. It evaluates the local receiver's availability and issues time-limited upload sessions.

### UploadRouteDecision

```python
class UploadRouteDecision(BaseModel):
    """Authoritative decision for where a client should upload files."""
    quote_id: str
    provider_kind: UploadProviderKind
    public_url: str
    session_token: str
    expires_at: datetime
    capabilities: list[UploadProviderCapability]
```

### Decision Logic (Hosted)

The broker uses the following logic to issue a route:

1. **Authorize**: Verifies client session, quote ownership, and status.
2. **Consult Local**: Checks for an active Local Receiver handshake (or assumes loopback/dev in v0).
3. **Issue Session**: Generates a cryptographically strong `session_token` for the chosen provider.
4. **Respond**: Returns the public URL and token to the client.

**Implementation**: `src/intake/services/upload_session_broker.py`
**Endpoint**: `POST /quotes/{id}/upload-route`


## Fallback Policy Configuration

### UploadFallbackPolicy

```python
class UploadFallbackPolicy(BaseModel):
    # Routing
    primary_provider: UploadProviderKind = UploadProviderKind.LOCAL_LOOPBACK_DEV
    fallback_providers: list[UploadProviderKind] = []
    
    # Retry logic
    max_retries: int = 3
    retry_delay_seconds: float = 2.0
    
    # Expiry
    fallback_expiry_minutes: int = 60  # Files in fallback for max 60 min
    
    # Requirements
    require_resumable_uploads: bool = False
    min_chunk_size_bytes: int = 5 * 1024 * 1024  # 5MB
    large_file_threshold_bytes: int = 100 * 1024 * 1024  # 100MB
```

### Policy Rules

**require_resumable_uploads**: If `True`, only providers supporting `RESUMABLE_UPLOAD` capability will be used for fallback. This ensures that large file uploads can resume if interrupted.

**large_file_threshold_bytes**: Files larger than this threshold require resumable upload support. Smaller files can use any provider.

**min_chunk_size_bytes**: Minimum chunk size for chunked/resumable uploads.

**fallback_expiry_minutes**: Maximum time a file can remain in fallback storage before being purged.

## Receiver Handshake

### Handshake Process

```
┌─────────────────┐                     ┌─────────────────┐
│     Client       │                     │ Local Receiver   │
├─────────────────┤                     ├─────────────────┤
│                 │                     │                 │
│  1. Handshake    │───────────────────▶│  1. Check        │
│      Request     │                     │     Readiness    │
│                 │                     │                 │
│  2. (wait)       │◀───────────────────│  2. Respond      │
│                 │                     │     ( Healthy/  │
│                 │                     │      Not Ready)│
│                 │                     │                 │
│  3. Upload or    │                     │                 │
│      Queue       │                     │                 │
└─────────────────┘                     └─────────────────┘
```

### ReceiverHandshakeResult

```python
class ReceiverHandshakeResult(BaseModel):
    receiver_kind: UploadProviderKind
    success: bool
    endpoint_url: Optional[str] = None
    handshake_latency_ms: Optional[float] = None
    error: Optional[str] = None
    receiver_version: Optional[str] = None
    requires_auth: bool = False
    auth_providers: list[str] = []
    handshake_timestamp: datetime = Field(default_factory=datetime.now)
```

### Handshake Endpoint

Local Console API adds:
```
GET /receiver/handshake
```

Response:
```json
{
  "receiver_kind": "local_loopback_dev",
  "success": true,
  "endpoint_url": "http://127.0.0.1:8001/upload",
  "handshake_latency_ms": 2.3,
  "error": null,
  "receiver_version": "0.1.0",
  "requires_auth": true,
  "auth_providers": ["sync_token", "device_auth"],
  "handshake_timestamp": "2024-05-12T10:00:00Z"
}
```

### Health Check Weight

The handshake latency is tracked so the router can prefer lower-latency providers:

```python
# Weight calculation for provider selection
HEALTH_WEIGHTS = {
    "latency": 0.4,      # Lower latency = higher score
    "capability": 0.3,   # More capabilities = higher score  
    "priority": 0.3,     # Explicit priority ordering
}

def calculate_provider_score(provider: UploadProviderPlan, latency: float) -> float:
    capability_score = len(provider.capabilities) / 8  # Normalized
    priority_score = 1.0 - (provider.priority / 10)  # Normalized
    latency_score = max(0, 1.0 - (latency / 500))  # 500ms = worst
    
    return (
        HEALTH_WEIGHTS["latency"] * latency_score +
        HEALTH_WEIGHTS["capability"] * capability_score +
        HEALTH_WEIGHTS["priority"] * priority_score
    )
```

## Upload Flow Sequence Diagram

```
Client                              Local Console              Hosted Backend
  │                                      │                      │
  │── Check local receiver handshake ────▶│                      │
  │◀───────── Handshake success ──────────│                      │
  │                                      │                      │
  │── Upload file ░══════════════════▶│                      │
  │◀────────────────── Upload receipt ─────│                      │
  │                                      │                      │
  │─── OR ─────────────────────────────────────────────────────────│
  │                                      │                      │
  │── Check local receiver handshake ────▶│ (timeout)              │
  │◀───────── Handshake failed ────────────│                      │
  │                                      │                      │
  │── Get fallback endpoint ───────────────────────────┬───────────▶│
  │◀─────── Fallback endpoint (Google Drive) ───────────┘───────────│
  │                                      │                      │
  │── Upload to fallback ───────────────────────────────────────────▶│
  │◀───────────────────────────────────── Buffer receipt ──────────│
  │                                      │                      │
  │◀─────────────── (Later) Sync from fallback ──────────│              │
  │                                      │                      │
```

## Error Handling & Retry

### Retry Strategy

```python
class RetryConfig:
    initial_delay: float = 1.0  # seconds
    max_delay: float = 30.0  # seconds
    backoff_multiplier: float = 2.0
    max_attempts: int = 3
    jitter: float = 0.1  # ±10% randomization


def calculate_retry_delay(attempt: int, config: RetryConfig) -> float:
    delay = min(
        config.initial_delay * (config.backoff_multiplier ** attempt),
        config.max_delay
    )
    # Add jitter to prevent thundering herd
    import random
    jitter_range = delay * config.jitter
    delay = delay + random.uniform(-jitter_range, jitter_range)
    return delay
```

### Retryable Errors

| Error Type | Retry | Fallback |
|------------|--------|----------|
| Network timeout | ✅ Yes | After 3 failures |
| Connection refused | ✅ Yes | After 3 failures |
| 502 Bad Gateway | ✅ Yes | After 3 failures |
| 503 Service Unavailable | ✅ Yes | After 3 failures |
| 429 Rate Limited | ⏳ Yes (with long delay) | After 3 failures |
| 404 Not Found | ❌ No | Try next provider |
| 401/403 Auth | ❌ No | N/A (fix auth) |
| 4xx (other) | ❌ No | Try next provider |
| 5xx (other) | ✅ Yes | After 3 failures |

### Non-Retryable Errors

These errors indicate a fundamental problem that retrying won't fix:
- Invalid API key/credentials
- File too large for provider limits
- Provider not configured
- Provider explicitly rejected the file type
- Storage quota exceeded

## Monitoring & Metrics

The upload router should track and expose metrics:

```python
class UploadMetrics:
    total_uploads: int
    uploads_by_provider: dict[UploadProviderKind, int]
    upload_errors_by_provider: dict[UploadProviderKind, int]
    retry_counts: dict[int, int]  # attempt count -> occurrences
    fallback_usage: int
    avg_upload_latency_ms: dict[UploadProviderKind, float]
    files_in_fallback: int
    fallback_expiry_count: int
```

API endpoint:
```
GET /metrics/upload
```

## Provider Health Checks

Each provider exposes a health check:

```python
class ProviderHealthCheck(BaseModel):
    kind: UploadProviderKind
    healthy: bool
    latency_ms: Optional[float] = None
    last_checked: datetime = Field(default_factory=datetime.now)
    error: Optional[str] = None
```

Health is checked before routing decisions:
- Every 30 seconds for configured providers
- On-demand before each upload
- Async/non-blocking

## Configuration Management

Provider configuration is stored with full redaction:

```python
@dataclass
class ProviderConfiguration:
    kind: UploadProviderKind
    # Encrypted sensitive data
    encrypted_config: bytes
    # Public non-sensitive metadata
    display_name: str
    capabilities: list[UploadProviderCapability]
    priority: int
    enabled: bool
```

Configuration is NEVER returned in full to the client. Only redacted versions:

```python
class ProviderConfigPublic(BaseModel):
    kind: UploadProviderKind
    display_name: str
    capabilities: list[UploadProviderCapability]
    status: UploadProviderStatus
    priority: int
    enabled: bool
    # No secrets, no sensitive data
```

## Security Considerations

### Token Isolation

Each upload receives temporary, single-use tokens:
- Upload session token (valid for 10 minutes)
- Specific to one file/one provider
- Cannot be reused for other operations
- Tied to client session

### Endpoint Restrictions

Fallback provider endpoints are:
- gated by rate limits
- Valid for specific file size ranges
- Limited in concurrent uploads per client
- Logged for audit

###Audit Trail

All uploads are logged with:
- Client identifier (hashed)
- Provider choice
- Route decision reason
- File metadata (name, size, type - NOT content)
- Timestamp
- Success/failure
- Duration

**Never logged:**
- File content
- Full local paths
- Provider credentials
- Unhashed client identifiers

## Future Enhancements

1. **Intelligent Routing Based on File Type**
   - Small files (<5MB): Any provider
   - Large files (>100MB): Require resumable upload + chunking
   - Encrypted files: Prefer E2EE-capable providers

2. **Geographic Routing**
   - Route to nearest fallback provider
   - Consider client location in decision

3. **Cost-Based Routing**
   - Track egress costs per provider
   - Prefer lowest-cost route

4. **Quota-Aware Routing**
   - Track storage usage per provider
   - Avoid providers nearing quota limits

5. **Multi-Provider Parallel Upload**
   - Upload to multiple providers simultaneously
   - Use first successful result
   - Improves reliability for critical files
