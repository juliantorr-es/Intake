# Host Bootstrapping

Host bootstrapping is the process of provisioning, configuring, deploying, verifying, and registering a Hosted Intake backend on common webhosts using the Local Console.

## Product Doctrine

- **Guided Deployment:** Host bootstrapping is guided deployment, not magic cloud control.
- **Provider Adapters:** Railway is the first-class target. The system uses a provider adapter architecture to support other hosts (e.g., Render, Fly.io) in the future.
- **Data Locality:** Provider tokens and secrets stay local. Local private keys (e.g., local private decrypt keys, local private signing keys) are **never** deployed to the hosted backend.
- **Safe Artifacts:** Generated artifacts are safe to inspect and are output to a safe build directory (e.g., `.build/intake/deploy/railway/...`).
- **Deployment Receipts:** Deployment receipts act as evidence, not secrets.

## Key Authority separation

If the current dev encryption key is still required by hosted runtime, it is strictly documented as a bootstrap-only and risky operation. We do not claim production local-only decrypt authority until public-key/envelope encryption removes the hosted decrypt capability.

## Railway Dry-Run Bootstrap

### Status: IMPLEMENTED (Non-Mutating)

The Railway dry-run bootstrap feature provides complete deployment readiness checking and plan generation WITHOUT performing any actual deployment or cloud mutations.

### Dry-Run Service

`RailwayDryRunBootstrapService` (`src/intake/deploy/railway_dry_run.py`) provides:

1. **CLI Detection** (`check_railway_cli()`):
   - Checks if `railway` CLI is installed
   - Retrieves CLI version via `railway --version`
   - Returns CLI path via `which railway` or `command -v`
   - Multiple detection methods with graceful fallback

2. **Auth Detection** (`check_railway_auth()`):
   - Scans for Railway config files (`.railway/config.json`, `.railway/credentials`, etc.)
   - Infers authentication state from file presence
   - Does NOT call `railway login` or `railway login status`
   - Conservative: unknown if no config files found

3. **Project Detection** (`check_railway_project()`):
   - Looks for `railway.json` or `.railway.json` in working directory
   - Indicates project linkage
   - Does NOT call `railway projects` or `railway link`

4. **Dry-Run Plan Generation** (`build_dry_run_plan()`):
   - Generates unique plan_id
   - Checks CLI, auth, and project state
   - Generates artifact paths (but doesn't write them by default)
   - Returns ALL commands as text strings only

### Commands That Would Run (Reference Only)

```bash
# INSTALL REQUIRED: npm i -g @railway/cli

# Like: railway login
# Like: railway link
# Like: railway init (in /path/to/project)
# Like: railway variables set INTAKE_ENV=production
# Like: railway variables set INTAKE_BASE_URL=https://your-app.up.railway.app
# Like: railway variables set INTAKE_RP_ID=your-domain.com
# Like: railway variables set INTAKE_RP_NAME=Intake
# Like: railway variables set INTAKE_ORIGIN=https://your-app.up.railway.app
# Like: railway variables set INTAKE_DATABASE_URL=<your-db-url>
# Like: railway variables set INTAKE_SESSION_SECRET=<generated-secret>
# Like: railway variables set INTAKE_LOCAL_SYNC_TOKEN=<generated-token>
# NOTE: INTAKE_LOCAL_SIGNING_KEY and other local-only keys are NOT set
# NOTE: These commands are for REFERENCE ONLY - they have not been executed
# To actually deploy: railway up
```

**CRITICAL**: None of these commands are executed by the service. They are returned as text strings in the plan only.

### Environment Variable Classification

**Hosted-Safe (included in deployment plans):**
```
INTAKE_ENV              # Deployment environment
INTAKE_BASE_URL        # Public URL
INTAKE_RP_ID           # WebAuthn RP ID
INTAKE_RP_NAME         # WebAuthn RP Name
INTAKE_ORIGIN          # Public origin
INTAKE_DATABASE_URL    # Database connection (REDACTED in examples)
INTAKE_SESSION_SECRET  # Session signing (REDACTED in examples)
INTAKE_LOCAL_SYNC_TOKEN # Sync auth (REDACTED in examples)
```

**Forbidden Local-Only (NEVER included):**
```
INTAKE_LOCAL_SIGNING_KEY       # Local private signing key
INTAKE_LOCAL_PRIVATE_DECRYPT_KEY # Local decrypt key
INTAKE_DEV_ENCRYPTION_KEY      # Dev symmetric key (bootstrap only)
```

### Dry-Run Plan Outputs

The `RailwayDryRunPlan` dataclass contains:

```python
# Identification
plan_id: str
created_at: datetime

# CLI State
railway_cli_present: bool
railway_cli_version: Optional[str]
railway_cli_path: Optional[str]

# Auth/Project State
railway_authenticated: Optional[bool]  # None = unknown
railway_project_linked: Optional[bool]  # None = unknown

# Environment Variables
required_env_vars: list[DeploymentEnvironmentSpec]
forbidden_env_vars: list[DeploymentEnvironmentSpec]

# Artifacts (generated as text, not written by default)
generated_artifact_paths: list[str]
artifact_contents: dict[str, str]

# Commands (TEXT ONLY - never executed)
commands_that_would_run: list[str]

# For User
next_manual_steps: list[str]
warnings: list[str]
errors: list[str]
blocking_issues: list[str]

# Status Properties
can_attempt_deployment: bool  # CLI present, no blocking issues
is_ready: bool  # Fully ready (CLI + auth + project + no issues)
```

### Local Console API Integration

The Local Console API (`src/intake/local_console/api.py`) provides endpoints:

```
GET /deploy/status              -> DeployReadinessResponse
GET /deploy/railway/dry-run     -> RailwayDryRunPlanResponse
```

**DeployReadinessResponse:**
- Status of Railway CLI (present/version)
- Authenticated state (unknown/authenticated/not)
- Project linkage state
- Ready status (cli_missing, ready_for_setup, fully_ready)
- Recommended next step
- Dry-run only flag

**RailwayDryRunPlanResponse:**
- Plan ID
- CLI info
- Auth/project info
- Blocking issues
- Warnings
- Next manual steps
- Example commands (text only)

### Safety Guarantees

The Railway dry-run service guarantees:

1. **No mutating commands executed**: Only `railway --version`, `which railway`, and file checks are run
2. **No Railway API calls**: Never calls `railway login status` or any other API
3. **No resource creation**: Never calls `railway init`, `railway link`, `railway up`
4. **No variable setting**: Never calls `railway variables set`
5. **Commands are text only**: All deployment commands are returned as strings, never executed
6. **Safe file operations**: Only reads local config files, never writes/mutates
7. **Conservative auth detection**: Auth state is inferred from files, not from API calls

### Usage Example

```python
from intake.deploy.railway_dry_run import RailwayDryRunBootstrapService

service = RailwayDryRunBootstrapService()

# Check environment
env_info = service.inspect_environment()
print(f"Railway CLI present: {env_info['railway_cli_present']}")
print(f"Railway CLI version: {env_info['railway_cli_version']}")

# Build dry-run plan
plan = service.build_dry_run_plan(app_name="my-intake")

# Review plan
print(f"Plan ID: {plan.plan_id}")
print(f"CLI present: {plan.railway_cli_present}")
print(f"Blocking issues: {plan.blocking_issues}")
print(f"Commands that would run:")
for cmd in plan.commands_that_would_run:
    print(f"  {cmd}")

# Validate artifacts (without writing)
validation = service.validate_artifacts(plan)
print(f"Artifacts valid: {validation['valid']}")
print(f"Issues: {validation['issues']}")

# Explain next steps
steps = service.explain_next_manual_steps()
for step in steps:
    print(step)
```

### Railway Adapter Integration

The `RailwayDeploymentAdapter` (`src/intake/deploy/adapters/railway.py`) now integrates with the dry-run service:

```python
adapter = RailwayDeploymentAdapter()

# Standard deployment planning
plan = adapter.plan_deployment("intake", {})
artifacts = adapter.write_artifacts(plan, ".build/intake/deploy/railway")

# Dry-run readiness check
readiness = adapter.verify_readiness()
# Returns:
# {
#     "cli_installed": True/False,
#     "cli_version": "4.0.0" or None,
#     "authenticated": True/False or None,
#     "project_linked": True/False or None,
#     "ready": True/False,
#     "is_fully_ready": True/False,
#     "blocking_issues": [...],
#     "warnings": [...],
#     "note": "Non-mutating Railway dry-run bootstrap check"
# }

# Full dry-run plan
full_plan = adapter.build_dry_run_plan("intake")
# Returns RailwayDryRunPlan with full details
```
