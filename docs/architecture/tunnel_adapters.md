# Tunnel Adapter Dry-Run Scaffolding

## Overview

The Tunnel Adapter module provides **dry-run only** scaffolding for Tailscale Funnel and Cloudflare Tunnel integration. This module is designed for:

- **Read-only CLI detection** - Checking if tunnel CLIs are installed
- **Version parsing** - Reading version information from installed CLIs
- **Text-only command generation** - Generating dry-run plans with commands that are NEVER executed
- **Exposure policy enforcement** - Ensuring Local Console is never exposed via tunnel

## Design Principles

### Never Execute

**NO tunnel commands are ever executed.** All commands in dry-run plans are:
- Generated as text only
- Marked with `would_execute=False`
- Stored in `commands_that_would_run` lists
- Require explicit approval for any real activation

### Read-Only CLI Checks

The module only performs read-only operations:
- `shutil.which()` - Find executable in PATH
- `os.access()` - Check file permissions
- `subprocess.run(capture_output=True)` - Read version output (stdout only)

### Loopback-Only by Default

All tunnel adapter plans:
- Default to disabled (`enabled=False`)
- Are loopback-only (`loopback_only_default=True`)
- Require explicit approval (`explicit_approval_required=True`)
- Expose only receiver API, never Local Console (`expose_console_api=False`)

### No Secrets or Credentials

- No API tokens or authentication credentials are stored or used
- No mutable commands are generated (install, auth, login, etc.)
- Version detection only uses public CLI commands

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Local Console API                         │
├─────────────────────────────────────────────────────────────────┤
│  GET /tunnel/status           - Get all tunnel adapter status   │
│  GET /tunnel/{provider}/dry-run - Get dry-run plan for provider  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    TunnelAdapterService                           │
├─────────────────────────────────────────────────────────────────┤
│  detect_all_clis()            - Detect all tunnel CLIs           │
│  generate_dry_run_plan()      - Generate text-only plan          │
│  get_all_plans()              - Get summary of all plans         │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────────────┼───────────────────────┐
              ▼                       ▼                       ▼
┌─────────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│ TailscaleFunnel...   │ │ CloudflareTunnel. │ │    Models         │
│ DryRunAdapter        │ │ DryRunAdapter     │ │                  │
├─────────────────────┤ ├──────────────────┤ ├──────────────────┤
│ - check_cli_present  │ │ - check_cli_...   │ │ TunnelProvider... │
│ - build_dry_run_plan │ │ - build_dry_run.. │ │ TunnelCLIStatus   │
│ - get_version()      │ │ - get_version()   │ │ TunnelDryRunPlan │
└─────────────────────┘ └──────────────────┘ │ TunnelCommandPlan │
                                                │ TunnelExposure... │
                                                └──────────────────┘
```

## Models

### TunnelProviderKind

Supported tunnel providers:
- `TAILSCALE_FUNNEL` - Tailscale Funnel
- `CLOUDFLARE_TUNNEL` - Cloudflare Tunnel (cloudflared)

### TunnelReadinessStatus

Readiness states:
- `NOT_INSTALLED` - CLI not found
- `INSTALLED` - CLI found but not configured
- `READY_FOR_DRY_RUN` - CLI found and ready for planning
- `READY_FOR_ACTIVATION` - Ready for real activation (requires approval)

### TunnelCLIStatus

Status of CLI detection:
- `provider` - Tunnel provider kind
- `cli_available` - Whether CLI is in PATH
- `cli_path` - Full path to CLI executable
- `version` - Detected version string
- `executable` - Whether CLI is executable
- `error` - Error message if detection failed

### TunnelCommandPlan

A single command in a dry-run plan:
- `command` - Command text (NEVER executed)
- `description` - Human-readable description
- `safety` - Safety classification (READ_ONLY, NEEDS_APPROVAL, UNSAFE)
- `would_execute` - Always `False` for dry-run
- `creates_public_endpoint` - Whether command would create public access
- `may_incur_costs` - Whether command could incur costs

### TunnelExposurePolicy

Policy for tunnel exposure (defaults to safe):
- `enabled` - `False` (disabled by default)
- `loopback_only_default` - `True`
- `explicit_approval_required` - `True`
- `expose_receiver_api` - `True` (receiver can be exposed)
- `expose_console_api` - `False` (Local Console NEVER exposed)
- `allowed_paths` - `["/receiver/*"]`
- `blocked_paths` - `["/", "/console/*", "/decrypt/*", "/review/*", "/api/*"]`

### TunnelDryRunPlan

Complete dry-run plan:
- `plan_id` - Unique plan identifier
- `provider` - Tunnel provider
- `readiness` - Current readiness status
- `activated` - Always `False` (dry-run only)
- `cli_status` - CLI detection result
- `commands_that_would_run` - List of text-only commands
- `exposure_policy` - Exposure policy
- `can_activate` - Whether plan could be activated
- `blocking_issues` - Issues preventing activation
- `warnings` - Safety warnings
- `next_steps` - Next steps for user

## Providers

### Tailscale Funnel

**CLI Detection:**
- Binary: `tailscale`
- Version command: `tailscale version`
- Minimum version: Any version (for dry-run)

**Generated Commands (TEXT ONLY):**
```
tailscale up
tailscale funnel 127.0.0.1:8001
tailscale funnel status
```

**Safety Classification:**
- `tailscale up` - NEEDS_APPROVAL (creates VPN connection)
- `tailscale funnel` - NEEDS_APPROVAL (creates public endpoint)
- `tailscale funnel status` - READ_ONLY

### Cloudflare Tunnel

**CLI Detection:**
- Binary: `cloudflared`
- Version command: `cloudflared version`
- Minimum version: Any version (for dry-run)

**Generated Commands (TEXT ONLY):**
```
cloudflared tunnel create intake-receiver
cloudflared tunnel route dns intake-receiver uploads
cloudflared tunnel run intake-receiver
cloudflared tunnel info
cloudflared version
```

**Safety Classification:**
- `tunnel create` - NEEDS_APPROVAL (creates tunnel)
- `tunnel route dns` - NEEDS_APPROVAL (configures DNS)
- `tunnel run` - NEEDS_APPROVAL (starts tunnel)
- `tunnel info` - READ_ONLY
- `version` - READ_ONLY

## API Endpoints

### GET /tunnel/status

Returns `TunnelAdapterPlanSummary` with:
- Plans for all providers
- Whether any plan is ready
- Whether all are disabled

**Example Response:**
```json
{
  "tailscale": {
    "plan_id": "dry_run_tailscale_funnel_abc123",
    "provider": "tailscale_funnel",
    "readiness": "not_installed",
    "activated": false,
    "cli_status": {
      "provider": "tailscale_funnel",
      "cli_available": false,
      "error": "CLI not installed"
    },
    "commands_that_would_run": [],
    "warnings": [...],
    "next_steps": [...]
  },
  "cloudflare": {...},
  "any_activated": false,
  "all_disabled": true,
  "any_ready": false
}
```

### GET /tunnel/{provider}/dry-run

Returns `TunnelDryRunPlan` for a specific provider.

**Path Parameters:**
- `provider` (required): `tailscale_funnel` or `cloudflare_tunnel`

**Example Response (CLI installed):**
```json
{
  "plan_id": "dry_run_tailscale_funnel_abc123",
  "provider": "tailscale_funnel",
  "readiness": "ready_for_dry_run",
  "activated": false,
  "cli_status": {
    "provider": "tailscale_funnel",
    "cli_available": true,
    "cli_path": "/usr/local/bin/tailscale",
    "version": "1.68.0"
  },
  "commands_that_would_run": [
    {
      "command": "tailscale up",
      "description": "Start Tailscale VPN connection",
      "safety": "needs_approval",
      "would_execute": false,
      "creates_public_endpoint": true
    }
  ],
  "exposure_policy": {
    "enabled": false,
    "loopback_only_default": true,
    "explicit_approval_required": true
  },
  "can_activate": true,
  "blocking_issues": [],
  "warnings": [...],
  "next_steps": [...]
}
```

## Testing

40 comprehensive tests cover:

### Model Tests
- Enum values validation
- Pydantic model creation and defaults
- Exposure policy defaults

### CLI Detection Tests
- Detection when CLI not installed
- Detection when CLI is installed
- Detection of all providers

### Dry-Run Plan Tests
- Plan generation for installed/uninstalled CLIs
- Command generation (text only)
- Warnings and next steps population
- All plans summary

### Adapter Tests
- Tailscale adapter interface
- Cloudflare adapter interface
- CLI presence checking
- Dry-run plan building
- Console never exposed

### Safety Tests
- No mutation commands in plans
- Exposure policy defaults to safe
- Plans never activated
- Commands are text only
- No secrets in commands

### Loopback-Only Tests
- Receiver port referenced in commands
- Loopback addressing in commands

### Integration Tests
- Service detects all providers
- Service generates all plans
- Both adapters have same interface

## Usage

```python
from intake.deploy.tunnel_adapters import (
    get_tunnel_adapter_service,
    TunnelProviderKind,
)

service = get_tunnel_adapter_service()

# Get status of all tunnel adapters
all_status = service.detect_all_clis()

# Generate dry-run plan for Tailscale
plan = service.generate_dry_run_plan(
    TunnelProviderKind.TAILSCALE_FUNNEL,
    receiver_port=8001,
)

# Get all plans
summary = service.get_all_plans()
```

## Future Work

- Real tunnel activation (behind explicit approval)
- Configuration persistence
- TLS certificate management
- Domain configuration
- Health checks for active tunnels
- Rate limiting for tunnel endpoints
- Authentication for exposed endpoints

## Security Considerations

1. **No execution**: All commands are text-only
2. **No secrets**: No credentials stored or used
3. **No exposure**: Local Console never exposed via tunnel
4. **Read-only**: Only version/status commands executed for detection
5. **Disabled by default**: All tunnels disabled until explicitly approved
6. **Loopback-first**: Default to loopback-only exposure
