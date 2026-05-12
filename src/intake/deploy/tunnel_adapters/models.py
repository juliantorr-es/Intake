"""Tunnel adapter models for dry-run scaffolding.

These models define the request/response structures for tunnel adapter
CLI detection and dry-run planning.

No secrets, tokens, or credentials are exposed in these models.
All commands are generated as inert text only.
"""

from datetime import datetime
from enum import StrEnum, auto
from typing import Any, Optional
from pydantic import BaseModel, Field, ConfigDict


# =============================================================================
# Enums
# =============================================================================

class TunnelProviderKind(StrEnum):
    """Supported tunnel provider kinds."""
    # Tailscale
    TAILSCALE_FUNNEL = "tailscale_funnel"
    
    # Cloudflare
    CLOUDFLARE_TUNNEL = "cloudflare_tunnel"


class TunnelAdapterCapability(StrEnum):
    """Capabilities that tunnel adapters may support."""
    # CLI Detection
    CLI_DETECTION = "cli_detection"
    VERSION_PARSING = "version_parsing"
    
    # Planning
    DRY_RUN_PLANNING = "dry_run_planning"
    COMMAND_GENERATION = "command_generation"
    
    # Safety
    READ_ONLY = "read_only"
    SAFETY_VALIDATION = "safety_validation"
    
    # Exposure control
    EXPOSURE_POLICY = "exposure_policy"
    DOMAIN_CONFIGURATION = "domain_configuration"
    CERTIFICATE_MANAGEMENT = "certificate_management"


class TunnelReadinessStatus(StrEnum):
    """Readiness status of a tunnel adapter."""
    NOT_INSTALLED = "not_installed"
    INSTALLED = "installed"
    AUTHENTICATED = "authenticated"
    CONFIGURED = "configured"
    READY_FOR_DRY_RUN = "ready_for_dry_run"
    READY_FOR_ACTIVATION = "ready_for_activation"
    ACTIVE = "active"
    ERROR = "error"


class TunnelCommandSafety(StrEnum):
    """Safety classification of generated commands."""
    # Safe for display and logging
    READ_ONLY = "read_only"  # e.g., version, status, info
    # Safe to display but requires approval to run
    NEEDS_APPROVAL = "needs_approval"  # e.g., tunnel create, tunnel run
    # Unsafe - could expose services or create costs
    UNSAFE = "unsafe"  # e.g., exposing internal services, public endpoints


# =============================================================================
# CLI Status Models
# =============================================================================

class TunnelCLIStatus(BaseModel):
    """Status of a tunnel CLI tool."""
    model_config = ConfigDict(json_schema_extra={
        "examples": [{
            "provider": "tailscale_funnel",
            "cli_available": True,
            "cli_path": "/usr/local/bin/tailscale",
            "version": "1.68.0",
            "min_version": "1.0.0",
            "satisfies_minimum": True,
        }]
    })
    
    provider: TunnelProviderKind
    cli_available: bool
    cli_path: Optional[str] = None
    version: Optional[str] = None
    min_version: Optional[str] = None
    satisfies_minimum: bool = False
    executable: bool = False
    error: Optional[str] = None


# =============================================================================
# Exposure Policy Models
# =============================================================================

class TunnelExposurePolicy(BaseModel):
    """Policy governing tunnel exposure.
    
    Default: disabled, loopback-only, explicit approval required.
    Receiver-only exposure. No Local Console dashboard exposure.
    """
    model_config = ConfigDict(json_schema_extra={
        "examples": [{
            "enabled": False,
            "loopback_only_default": True,
            "explicit_approval_required": True,
            "expose_receiver_api": True,
            "expose_console_api": False,
            "allowed_paths": ["/receiver/*"],
            "blocked_paths": ["/", "/console/*", "/decrypt/*", "/review/*"],
        }]
    })
    
    # Global control
    enabled: bool = False
    loopback_only_default: bool = True
    
    # Approval
    explicit_approval_required: bool = True
    approval_granted: bool = False
    
    # Path exposure
    expose_receiver_api: bool = True
    expose_console_api: bool = False  # Never expose Local Console via tunnel
    
    # Allowed/blocked paths
    allowed_paths: list[str] = ["/receiver/*"]
    blocked_paths: list[str] = ["/", "/console/*", "/decrypt/*", "/review/*", "/api/*"]
    
    # Security
    require_https: bool = True
    require_authentication: bool = False  # Future
    
    # Rate limiting (future)
    is_future: bool = True


# =============================================================================
# Command Models
# =============================================================================

class TunnelCommandPlan(BaseModel):
    """A single command that would be run as part of a tunnel plan.
    
    Commands are TEXT ONLY. Never executed.
    """
    model_config = ConfigDict(json_schema_extra={
        "examples": [{
            "command": "tailscale funnel 127.0.0.1:8001",
            "description": "Expose local receiver via Tailscale Funnel",
            "safety": "needs_approval",
            "would_execute": False,
            "creates_public_endpoint": True,
        }]
    })
    
    command: str  # The command text - NEVER executed
    description: str
    safety: TunnelCommandSafety = TunnelCommandSafety.NEEDS_APPROVAL
    would_execute: bool = False  # Always false - commands are text only
    requires_sudo: bool = False
    creates_public_endpoint: bool = True
    may_incur_costs: bool = False


class TunnelDryRunPlan(BaseModel):
    """A dry-run plan for tunnel configuration.
    
    No commands in this plan are executed. They are generated as text only.
    """
    model_config = ConfigDict(json_schema_extra={
        "examples": [{
            "plan_id": "tailscale_funnel_dry_run_001",
            "provider": "tailscale_funnel",
            "readiness": "ready_for_dry_run",
            "activated": False,
            "commands_that_would_run": [
                {"command": "tailscale funnel 127.0.0.1:8001", "would_execute": False}
            ],
            "exposure_policy": {"enabled": False, "explicit_approval_required": True},
        }]
    })
    
    plan_id: str
    provider: TunnelProviderKind
    readiness: TunnelReadinessStatus
    activated: bool = False  # Always false for dry-run
    
    # CLI status
    cli_status: TunnelCLIStatus
    
    # Commands (TEXT ONLY - NEVER EXECUTED)
    commands_that_would_run: list[TunnelCommandPlan] = []
    
    # Generation timestamp
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Safety
    exposure_policy: TunnelExposurePolicy = Field(default_factory=TunnelExposurePolicy)
    
    # Results
    can_activate: bool = False
    blocking_issues: list[str] = []
    warnings: list[str] = []
    next_steps: list[str] = []


# =============================================================================
# Adapter Base Model
# =============================================================================

class TunnelAdapterConfig(BaseModel):
    """Configuration for a tunnel adapter."""
    model_config = ConfigDict(json_schema_extra={
        "examples": [{
            "provider": "tailscale_funnel",
            "enabled": False,
            "receiver_port": 8001,
            "public_port": 443,
            "explicit_approval_required": True,
        }]
    })
    
    provider: TunnelProviderKind
    enabled: bool = False
    receiver_port: int = 8001
    public_port: int = 443
    explicit_approval_required: bool = True
    approval_granted: bool = False
    
    # Non-sensitive display name
    display_name: str = "Tunnel Adapter"
    description: str = "Dry-run only - commands are text only"


class TunnelAdapterPlanSummary(BaseModel):
    """Summary of tunnel adapter plans across all providers."""
    model_config = ConfigDict(json_schema_extra={
        "examples": [{
            "tailscale": {"readiness": "ready_for_dry_run", "activated": False},
            "cloudflare": {"readiness": "not_installed", "activated": False},
            "any_activated": False,
            "all_disabled": True,
        }]
    })
    
    tailscale: Optional[TunnelDryRunPlan] = None
    cloudflare: Optional[TunnelDryRunPlan] = None
    any_activated: bool = False
    all_disabled: bool = True
    any_ready: bool = False
