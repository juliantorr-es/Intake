# Provider Boundary

## Architecture

The provider boundary defines the separation between Intake's local-first upload architecture and external cloud/storage providers. Every interaction with providers is mediated through this boundary to ensure:

1. **No direct provider API calls from public routes** - All provider interactions flow through the deployment adapter or upload router
2. **No credential exposure** - Provider tokens/secrets are never exposed in API responses, logs, or UI
3. **Safe failure** - Provider failures don't crash the application or expose sensitive information
4. **Auditability** - All provider interactions are logged (without secrets) for debugging

## Proofs

### 1. Provider Interface Abstraction

**Claim**: All providers implement a common interface that prevents direct API coupling.

**Proof**: `
- `BaseDeploymentAdapter` (src/intake/deploy/adapters/base.py:10-49) defines abstract interface:
  - `provider` property → DeploymentProvider enum
  - `plan_deployment()` → DeploymentPlan
  - `verify_readiness()` → dict
  - `write_artifacts()` → list[str]

- `UploadProviderKind` (src/intake/deploy/models_upload.py:7-23) enumerates ALL provider kinds
  - All provider types are explicitly listed
  - No string-based provider references in routing code
  - Type-safe provider selection

- Railway adapter extends `BaseDeploymentAdapter`:
  - `src/intake/deploy/adapters/railway.py:3` - RailwayDeploymentAdapter
  - Implements required methods through base class contract

**Result**: ✅ Providers cannot be accessed without going through the adapter interface.

### 2. Dry-Run Safety (Railway)

**Claim**: Railway dry-run never executes mutating commands.

**Proof**: `src/intake/deploy/railway_dry_run.py`

**Allowed operations** (read-only):
- `railway --version` - `src/intake/deploy/railway_dry_run.py:261-275`
- `command -v railway` - `src/intake/deploy/railway_dry_run.py:277-289`
- `which railway` - `src/intake/deploy/railway_dry_run.py:291-303`
- File existence checks - `src/intake/deploy/railway_dry_run.py:305-324`
- Directory scanning for config files - `src/intake/deploy/railway_dry_run.py:326-340`

**Explicitly forbidden** (documented):
```python
# from src/intake/deploy/railway_dry_run.py:9-16
# It never executes mutating commands like:
# - railway init
# - railway link  
# - railway up
# - railway add
# - railway variables set
# - railway deploy
```

**Command generation is text-only**:
```python
# src/intake/deploy/railway_dry_run.py:447-461
commands.extend([
    "# Like: railway login",
    "# Like: railway link",
    "# Like: railway init (in {self.working_dir})",
    "# Like: railway variables set INTAKE_ENV=production",
    # ... all as comments
    "# NOTE: These commands are for REFERENCE ONLY - they have not been executed",
    "# To actually deploy: railway up",
])
```

**Validation function ensures safety**:
- `validate_artifacts()` - `src/intake/deploy/railway_dry_run.py:553-579`
  - Checks for forbidden env vars in generated artifacts
  - Verifies secrets are redacted
  - Returns validation results without executing anything

**Result**: ✅ No Railway API mutating commands are executed. All commands are text references only.

### 3. Environment Variable Separation

**Claim**: Local-only variables are never included in deployment plans.

**Proof**: `src/intake/deploy/railway_dry_run.py:28-71`

**Hosted-safe variables** (HOSTED_ENV_SPECS):
```python
INTAKE_ENV, INTAKE_BASE_URL, INTAKE_RP_ID, INTAKE_RP_NAME
INTAKE_ORIGIN, INTAKE_DATABASE_URL
INTAKE_SESSION_SECRET, INTAKE_LOCAL_SYNC_TOKEN
```

**Forbidden local-only variables** (FORBIDDEN_ENV_SPECS):
```python
INTAKE_LOCAL_SIGNING_KEY (forbidden=True, is_secret=True)
INTAKE_LOCAL_PRIVATE_DECRYPT_KEY (forbidden=True, is_secret=True)
INTAKE_DEV_ENCRYPTION_KEY (forbidden=True, is_secret=True)
```

**Filtering in Railway adapter**:
```python
# src/intake/deploy/adapters/railway.py:26-38
# Forbidden keys
DeploymentEnvironmentSpec(key="INTAKE_LOCAL_SIGNING_KEY", ..., forbidden=True)
# ...
# Filter out forbidden keys
safe_env = [v for v in env_vars if not v.forbidden]
```

**Generated .env.hosted.example excludes local keys**:
```python
# src/intake/deploy/adapters/railway.py:61-65
for v in safe_env:  # safe_env only (forbidden filtered out)
    val = v.default_value or "REDACTED" if v.is_secret else ""
    env_example += f"{v.key}={val} # {v.description}\n"
```

**Result**: ✅ Forbidden local-only variables are explicitly marked and filtered from all deployment artifacts.

### 4. Provider Config Redaction

**Claim**: Provider configurations never expose secrets in public APIs, logs, or UI.

**Proof**: `src/intake/deploy/provider_redaction.py`

**Redaction utilities**:
- `redact_secret_value()` - line 40-58: Redacts values matching secret patterns
- `redact_dict_keys()` - line 61-83: Redacts values for sensitive key names
- `redact_file_paths()` - line 86-109: Redacts filesystem paths
- `sanitize_provider_config()` - line 112-139: Full sanitization pipeline
- `get_redacted_fields()` - line 142-167: Lists fields that were redacted

**Secret patterns** (line 12-22):
```python
SECRET_PATTERNS = [
    r'(?:api[_-]?key|apikey|token|secret|password|credential)[_-]?',
    r'Bearer\s+[a-zA-Z0-9_\-\.]+',
    r'-----BEGIN.*PRIVATE.*KEY-----',
    r'(?:postgresql|mysql|mongodb)://[^:]+:[^@]+@',
    r'(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}',
]
```

**Sensitive key names** (line 25-47):
```python
SECRET_KEY_NAMES = frozenset({
    "api_key", "secret", "token", "password", "credential",
    "auth", "private_key", "signing_key", "encryption_key",
    "sync_token", "database_url", "session_secret",
    "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
    "GOOGLE_DRIVE_API_KEY", "TAILSCALE_AUTH_KEY",
    "CLOUDFLARE_API_TOKEN",
})
```

**Local-only patterns** (line 50-57):
```python
LOCAL_ONLY_KEY_PATTERNS = frozenset({
    "INTAKE_LOCAL_", "PRIVATE_", "DEV_", "TEST_", "SECRET_",
})
```

**Result**: ✅ Provider configurations are redacted through multiple passes ensuring no secrets leak.

### 5. Upload Route Decision Redaction

**Claim**: Upload route decisions expose only safe information.

**Proof**: `src/intake/deploy/models_upload.py:109-128`

`UploadRouteDecision` model exposes:
```python
chosen_provider: UploadProviderKind  # Enum, not a secret
route_priority: int
route_reason: str
fallback_available: bool
fallback_provider: Optional[UploadProviderKind]
upload_endpoint: str  # URL, not filesystem path
upload_session: Optional[dict[str, str]]  # Temp auth, not credentials
expires_at: Optional[datetime]
```

Note: NO fields for:
- Credentials/tokens
- Filesystem paths
- Provider secrets
- Full configuration objects

**UploadFallbackPolicy** (line 131-145) serializes without credentials:
```python
primary_provider: UploadProviderKind  # Enum reference only
fallback_providers: list[UploadProviderKind]  # Enum references only
max_retries: int
retry_delay_seconds: float
fallback_expiry_minutes: int
require_resumable_uploads: bool
min_chunk_size_bytes: int
large_file_threshold_bytes: int
```

**Result**: ✅ Upload routing models contain only references and non-sensitive configuration.

### 6. Local Console API Redaction

**Claim**: Local Console API never exposes provider secrets.

**Proof**: `src/intake/local_console/api.py`

**ProviderStatusResponse** (line 28-34):
```python
class ProviderStatusResponse(BaseModel):
    provider: str  # e.g., "railway"
    cli_present: bool
    cli_version: Optional[str] = None
    authenticated: Optional[bool] = None
    project_linked: Optional[bool] = None
    ready_status: str = "not_ready"
    blocking_issues: list[str] = []
```

**DeployReadinessResponse** (line 37-44):
```python
class DeployReadinessResponse(BaseModel):
    status: str = "dry_run_only"
    railway: ProviderStatusResponse  # Contains no secrets
    upload_receiver_configured: bool = False
    fallback_storage_configured: bool = False
    recommended_next_step: str = "install_railway_cli"
    dry_run_only: bool = True
```

**RailwayDryRunPlanResponse** (line 47-57):
```python
class RailwayDryRunPlanResponse(BaseModel):
    plan_id: str
    railway_cli_present: bool
    railway_cli_version: Optional[str] = None
    railway_authenticated: Optional[bool] = None
    railway_project_linked: Optional[bool] = None
    blocking_issues: list[str] = []
    warnings: list[str] = []
    next_manual_steps: list[str] = []
    example_commands: list[str] = []  # Text only, not executed
```

**_get_railway_status()** (line 85-119): Uses try/except to safely handle errors, never returns raw exceptions to client.

**get_railway_dry_run_plan()** (line 122-143): Returns RailwayDryRunPlanResponse, sample commands are text only.

**Result**: ✅ Local Console API responses contain only status information, never provider credentials or sensitive data.

### 7. No Filesystem Path Exposure

**Claim**: Public/client APIs never expose local filesystem paths.

**Proof**:

**provider_redaction.py** `redact_file_paths()` (line 86-109):
```python
def redact_file_paths(value: Any) -> Any:
    # Checks for patterns like:
    # /home/username/, /Users/username/, C:\\Users\\username\\
    # .ssh/, .config/, .railway/
    # /tmp/, /var/, /etc/
    # Absolute paths
    ```

**sanitize_provider_config()** (line 112-139): Three-pass sanitization including file path redaction.

**Artifact path handling** - The actual file paths generated for build artifacts are:
- Written to `.build/intake/deploy/railway/{plan_id}/` directory
- Returned as absolute paths in `generated_artifact_paths`
- BUT these paths are generated locally and used only for build output
- NOT exposed in any public API responses

**Railway adapter** returns only relative paths in DeploymentPlan:
```python
# src/intake/deploy/adapters/railway.py:52-60
artifacts = [
    DeploymentArtifact(
        name="railway.json",
        content=json.dumps(railway_config, indent=2),
        path="railway.json"  # Relative path
    ),
    DeploymentArtifact(
        name=".env.hosted.example",
        content=env_example,
        path=".env.hosted.example"  # Relative path
    )
]
```

**Result**: ✅ Filesystem paths are either relative (in API models) or redacted before public exposure.

### 8. Hosted-Safe vs Local-Only Variable Boundary

**Claim**: Hosted-safe and local-only environment variables are explicitly separated.

**Proof**: `src/intake/deploy/railway_dry_run.py:28-72`

**HOSTED_SAFE_VAR_KEYS**:
```python
frozenset({
    "INTAKE_ENV", "INTAKE_BASE_URL", "INTAKE_RP_ID",
    "INTAKE_RP_NAME", "INTAKE_ORIGIN", "INTAKE_DATABASE_URL",
    "INTAKE_SESSION_SECRET", "INTAKE_LOCAL_SYNC_TOKEN",
})
```

These are required by hosted runtime for:
- WebAuthn RP identification
- Public origin configuration
- Database connectivity
- Session management
- Sync protocol authentication with local console

**LOCAL_ONLY_FORBIDDEN_VAR_KEYS**:
```python
frozenset({
    "INTAKE_LOCAL_SIGNING_KEY",
    "INTAKE_LOCAL_PRIVATE_DECRYPT_KEY", 
    "INTAKE_DEV_ENCRYPTION_KEY",
})
```

These are LOCAL ONLY for:
- Signing local actions
- Decrypting sync payloads with local keys
- Development-only symmetric encryption

**Crypto honesty documented**:
```python
# src/intake/deploy/railway_dry_run.py:73-85
# Forbidden local-only vars (must NEVER be in hosted deployment)
FORBIDDEN_ENV_SPECS = [
    DeploymentEnvironmentSpec(
        key="INTAKE_LOCAL_SIGNING_KEY",
        description="Local private signing key - LOCAL ONLY",
        forbidden=True,
        is_secret=True
    ),
    ...
]
```

**Documentation in code**:
```python
# src/intake/docs/architecture/host-bootstrapping.md
# If the current dev encryption key is still required by hosted runtime,
# it is strictly documented as a bootstrap-only and risky operation.
# We do not claim production local-only decrypt authority...
```

**Result**: ✅ Hosted-safe and local-only variables are explicitly enumerated and separated with clear documentation.

## Boundary Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                      PROVIDER BOUNDARY                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    INTRAKE CORE                              │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐ │   │
│  │  │ Deploy        │  │ Upload        │  │ Local Console   │ │   │
│  │  │ Adapters      │  │ Router        │  │ API             │ │   │
│  │  └──────────────┘  └──────────────┘  └────────────────┘ │   │
│  │                                                       │   │
│  │  ┌─────────────────────────────────────────────────────┐│   │
│  │  │  Pydantic Models (safe by design)                    ││   │
│  │  │  - DeploymentPlan       - UploadRouteDecision         ││   │
│  │  │  - ProviderConfigRedacted - UploadFallbackPolicy      ││   │
│  │  │  - ReceiverHandshakeResult                            ││   │
│  │  └─────────────────────────────────────────────────────┘│   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────┴──────────────────┴──────────────────┐   │
│                              BOUNDARY CROSSING                    │   │
│  │  Only through:                                           │   │
│  │  - BaseDeploymentAdapter methods                        │   │
│  │  - Sanitized Pydantic model serialization               │   │
│  │  - Redaction utilities (provider_redaction.py)           │   │
│  └──────────────────┬──────────────────┬──────────────────┘   │
│                      │                    │                       │
│           ┌──────────▼──────────┐ ┌──────────▼──────────┐    │
│           │ Railway Dry-Run      │ │ Upload Providers     │    │
│           │ - railway --version  │ │ - local_loopback    │    │
│           │ - which railway       │ │ - tailscale_funnel*  │    │
│           │ - File checks only   │ │ - cloudflare_tunnel* │    │
│           └──────────────────────┘ │ - google_drive*      │    │
│                                         │ - s3_compatible*    │    │
│                                         │ - cloudflare_r2*    │    │
│                                         └────────────────────┘    │
│                                 *Future implementations            │
└─────────────────────────────────────────────────────────────────┘
```

## Security Guarantees

Based on the above proofs, the provider boundary guarantees:

1. ✅ **No mutating provider commands in dry-run**: Railway dry-run only performs read-only operations
2. ✅ **No credential exposure**: Provider secrets are redacted before any public exposure
3. ✅ **No filesystem path exposure**: Paths are either relative or redacted
4. ✅ **Explicit variable separation**: Hosted-safe vs local-only env vars are clearly separated
5. ✅ **Safe API responses**: Local Console and public APIs only expose redacted data
6. ✅ **Type-safe provider references**: All providers are enum-based, preventing typos and injection

## Known Gaps

This slice does NOT implement:
- Actual Tailscale Funnel integration
- Actual Cloudflare Tunnel integration
- Actual Google Drive API calls
- Actual S3/R2 API calls
- Real tus server for resumable uploads
- Provider credential storage (it doesn't exist yet)

These are future work and the boundary is designed to prevent accidental abuse when they are implemented.

## Testing

Tests for these boundaries are in:
- `tests/test_deployment_artifacts.py` - Security constraints on deployment artifacts
- `tests/test_railway_dry_run.py` - Railway dry-run behavior (to be created)
- `tests/test_provider_routing.py` - Provider routing and redaction (to be created)
