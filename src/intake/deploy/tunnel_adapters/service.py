"""Tunnel Adapter Service - dry-run only.

Provides read-only CLI detection and dry-run planning for tunnel adapters.
NO tunnel commands are executed. Only CLI detection and text command generation.
"""

import logging
import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from enum import auto, StrEnum
from typing import Any, Optional

from intake.deploy.tunnel_adapters.models import (
    TunnelAdapterCapability,
    TunnelAdapterConfig,
    TunnelAdapterPlanSummary,
    TunnelCLIStatus,
    TunnelCommandPlan,
    TunnelCommandSafety,
    TunnelDryRunPlan,
    TunnelExposurePolicy,
    TunnelProviderKind,
    TunnelReadinessStatus,
)

logger = logging.getLogger(__name__)


@dataclass
class CLIDetectionResult:
    """Result of detecting a CLI tool."""
    provider: TunnelProviderKind
    found: bool
    path: Optional[str] = None
    version: Optional[str] = None
    error: Optional[str] = None


class TunnelAdapterService:
    """Service for detecting and planning tunnel adapters.
    
    This service:
    - Detects CLI tools (read-only)
    - Parses version information (read-only)
    - Generates dry-run plans (text-only commands)
    - NEVER executes tunnel commands
    """
    
    def __init__(self):
        self._adapters: dict[TunnelProviderKind, Any] = {}
    
    def register_adapter(self, adapter: Any) -> None:
        """Register a tunnel adapter."""
        self._adapters[adapter.provider] = adapter
    
    def detect_all_clis(self) -> dict[TunnelProviderKind, TunnelCLIStatus]:
        """Detect all tunnel CLI tools.
        
        Uses read-only checks only:
        - shutil.which() - finds executable in PATH
        - subprocess.run() with stdout=PIPE, stderr=PIPE - reads version
        - Never executes mutation commands
        """
        results = {}
        
        for provider in TunnelProviderKind:
            if provider == TunnelProviderKind.TAILSCALE_FUNNEL:
                results[provider] = self._detect_tailscale()
            elif provider == TunnelProviderKind.CLOUDFLARE_TUNNEL:
                results[provider] = self._detect_cloudflared()
        
        return results
    
    def _detect_tailscale(self) -> TunnelCLIStatus:
        """Detect Tailscale CLI."""
        # Check if tailscale is in PATH
        path = shutil.which("tailscale")
        
        if not path:
            return TunnelCLIStatus(
                provider=TunnelProviderKind.TAILSCALE_FUNNEL,
                cli_available=False,
                error="tailscale not found in PATH",
            )
        
        # Check if executable
        is_executable = True
        try:
            # Read-only: check if file exists and is executable
            import os
            is_executable = os.access(path, os.X_OK)
        except Exception:
            is_executable = False
        
        # Get version (read-only command)
        version = None
        try:
            result = subprocess.run(
                [path, "version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                # Parse version from output
                # tailscale version output: "tailscale version: 1.x.x"
                version = result.stdout.strip()
            elif "not found" in result.stderr or "not installed" in result.stderr:
                return TunnelCLIStatus(
                    provider=TunnelProviderKind.TAILSCALE_FUNNEL,
                    cli_available=False,
                    error=f"tailscale not found: {result.stderr[:100]}",
                )
        except subprocess.TimeoutExpired:
            pass
        except Exception as e:
            logger.debug(f"Error detecting tailscale version: {e}")
        
        return TunnelCLIStatus(
            provider=TunnelProviderKind.TAILSCALE_FUNNEL,
            cli_available=True,
            cli_path=path,
            version=version,
            executable=is_executable,
            satisfies_minimum=True,  # Any version satisfies for dry-run
        )
    
    def _detect_cloudflared(self) -> TunnelCLIStatus:
        """Detect Cloudflare Tunnel CLI."""
        # Check if cloudflared is in PATH
        path = shutil.which("cloudflared")
        
        if not path:
            return TunnelCLIStatus(
                provider=TunnelProviderKind.CLOUDFLARE_TUNNEL,
                cli_available=False,
                error="cloudflared not found in PATH",
            )
        
        # Check if executable
        is_executable = True
        try:
            import os
            is_executable = os.access(path, os.X_OK)
        except Exception:
            is_executable = False
        
        # Get version (read-only command)
        version = None
        try:
            result = subprocess.run(
                [path, "version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                version = result.stdout.strip()
            elif "not found" in result.stderr or "not installed" in result.stderr:
                return TunnelCLIStatus(
                    provider=TunnelProviderKind.CLOUDFLARE_TUNNEL,
                    cli_available=False,
                    error=f"cloudflared not found: {result.stderr[:100]}",
                )
        except subprocess.TimeoutExpired:
            pass
        except Exception as e:
            logger.debug(f"Error detecting cloudflared version: {e}")
        
        return TunnelCLIStatus(
            provider=TunnelProviderKind.CLOUDFLARE_TUNNEL,
            cli_available=True,
            cli_path=path,
            version=version,
            executable=is_executable,
            satisfies_minimum=True,
        )
    
    def generate_dry_run_plan(
        self,
        provider: TunnelProviderKind,
        receiver_port: int = 8001,
    ) -> TunnelDryRunPlan:
        """Generate a dry-run plan for a tunnel provider.
        
        The plan includes:
        - CLI status detection
        - Commands that would run (TEXT ONLY - NEVER EXECUTED)
        - Readiness status
        - Exposure policy (disabled by default)
        
        Args:
            provider: The tunnel provider
            receiver_port: The local receiver port (default: 8001)
        
        Returns:
            Dry-run plan with text-only commands
        """
        import secrets
        import uuid
        
        plan_id = f"dry_run_{provider.value}_{secrets.token_hex(4)}"
        
        # Get CLI status
        cli_status = self.detect_all_clis().get(provider)
        
        if not cli_status or not cli_status.cli_available:
            return TunnelDryRunPlan(
                plan_id=plan_id,
                provider=provider,
                readiness=TunnelReadinessStatus.NOT_INSTALLED,
                activated=False,
                cli_status=TunnelCLIStatus(
                    provider=provider,
                    cli_available=False,
                    error="CLI not installed",
                ),
                commands_that_would_run=[],
                exposure_policy=TunnelExposurePolicy(),
                blocking_issues=[f"{provider.value} CLI not installed"],
                warnings=[
                    "Commands are TEXT ONLY - NEVER EXECUTED in dry-run mode",
                    "CLI must be installed before dry-run planning",
                    "Receiver will remain loopback-only until tunnel is configured",
                ],
                next_steps=[
                    "Install the CLI tool",
                    "Review generated commands once CLI is available",
                    "Grant explicit approval if ready to activate",
                ],
            )
        
        # Generate commands (TEXT ONLY - NEVER EXECUTED)
        commands = self._generate_commands(provider, receiver_port)
        
        # Determine readiness
        if cli_status.cli_available and cli_status.executable:
            readiness = TunnelReadinessStatus.READY_FOR_DRY_RUN
            if len(commands) > 0:
                can_activate = True
            else:
                readiness = TunnelReadinessStatus.READY_FOR_ACTIVATION
        else:
            readiness = TunnelReadinessStatus.NOT_INSTALLED
            can_activate = False
        
        return TunnelDryRunPlan(
            plan_id=plan_id,
            provider=provider,
            readiness=readiness,
            activated=False,  # Always false for dry-run
            cli_status=cli_status,
            commands_that_would_run=commands,
            exposure_policy=TunnelExposurePolicy(),
            can_activate=can_activate,
            blocking_issues=[],
            warnings=[
                "Commands are TEXT ONLY - NEVER EXECUTED in dry-run mode",
                "Real activation requires explicit approval",
                "Receiver will remain loopback-only until explicitly configured",
            ],
            next_steps=[
                "Review generated commands",
                "Grant explicit approval if ready to activate",
                "Configure exposure policy if enabling",
            ],
        )
    
    def _generate_commands(
        self,
        provider: TunnelProviderKind,
        receiver_port: int = 8001,
    ) -> list[TunnelCommandPlan]:
        """Generate text-only commands for tunnel configuration.
        
        These commands are NEVER EXECUTED. They are generated as examples
        of what would be run for real activation.
        
        Args:
            provider: The tunnel provider
            receiver_port: The local receiver port
        
        Returns:
            List of command plans (text only)
        """
        commands = []
        
        if provider == TunnelProviderKind.TAILSCALE_FUNNEL:
            # Tailscale Funnel commands (text only)
            commands.extend([
                TunnelCommandPlan(
                    command=f"tailscale up",
                    description="Start Tailscale VPN connection",
                    safety=TunnelCommandSafety.NEEDS_APPROVAL,
                    would_execute=False,
                    creates_public_endpoint=True,
                    may_incur_costs=False,
                ),
                TunnelCommandPlan(
                    command=f"tailscale funnel 127.0.0.1:{receiver_port}",
                    description="Expose local receiver via Tailscale Funnel",
                    safety=TunnelCommandSafety.NEEDS_APPROVAL,
                    would_execute=False,
                    creates_public_endpoint=True,
                    may_incur_costs=False,
                ),
                TunnelCommandPlan(
                    command="tailscale funnel status",
                    description="Check Funnel status",
                    safety=TunnelCommandSafety.READ_ONLY,
                    would_execute=False,
                    creates_public_endpoint=False,
                    may_incur_costs=False,
                ),
            ])
        
        elif provider == TunnelProviderKind.CLOUDFLARE_TUNNEL:
            # Cloudflare Tunnel commands (text only)
            tunnel_name = "intake-receiver"
            commands.extend([
                TunnelCommandPlan(
                    command=f"cloudflared tunnel create {tunnel_name}",
                    description="Create a new Cloudflare Tunnel",
                    safety=TunnelCommandSafety.NEEDS_APPROVAL,
                    would_execute=False,
                    creates_public_endpoint=True,
                    may_incur_costs=True,  # Cloudflare Tunnel is free but may have costs at scale
                ),
                TunnelCommandPlan(
                    command=f"cloudflared tunnel route dns {tunnel_name} uploads",
                    description="Route DNS for tunnel",
                    safety=TunnelCommandSafety.NEEDS_APPROVAL,
                    would_execute=False,
                    creates_public_endpoint=True,
                    may_incur_costs=False,
                ),
                TunnelCommandPlan(
                    command=f"cloudflared tunnel run {tunnel_name}",
                    description="Run the tunnel",
                    safety=TunnelCommandSafety.NEEDS_APPROVAL,
                    would_execute=False,
                    creates_public_endpoint=True,
                    may_incur_costs=False,
                ),
                TunnelCommandPlan(
                    command="cloudflared tunnel info",
                    description="Show tunnel information",
                    safety=TunnelCommandSafety.READ_ONLY,
                    would_execute=False,
                    creates_public_endpoint=False,
                    may_incur_costs=False,
                ),
                TunnelCommandPlan(
                    command="cloudflared version",
                    description="Check cloudflared version",
                    safety=TunnelCommandSafety.READ_ONLY,
                    would_execute=False,
                    creates_public_endpoint=False,
                    may_incur_costs=False,
                ),
            ])
        
        return commands
    
    def get_all_plans(self) -> TunnelAdapterPlanSummary:
        """Get dry-run plans for all tunnel providers."""
        tailscale_plan = self.generate_dry_run_plan(
            TunnelProviderKind.TAILSCALE_FUNNEL, receiver_port=8001
        )
        cloudflare_plan = self.generate_dry_run_plan(
            TunnelProviderKind.CLOUDFLARE_TUNNEL, receiver_port=8001
        )
        
        return TunnelAdapterPlanSummary(
            tailscale=tailscale_plan,
            cloudflare=cloudflare_plan,
            any_activated=tailscale_plan.activated or cloudflare_plan.activated,
            all_disabled=not tailscale_plan.activated and not cloudflare_plan.activated,
            any_ready=(
                tailscale_plan.readiness == TunnelReadinessStatus.READY_FOR_DRY_RUN
                or cloudflare_plan.readiness == TunnelReadinessStatus.READY_FOR_DRY_RUN
            ),
        )


# Singleton service
def get_tunnel_adapter_service() -> TunnelAdapterService:
    """Get the singleton tunnel adapter service."""
    if not hasattr(get_tunnel_adapter_service, "_instance"):
        get_tunnel_adapter_service._instance = TunnelAdapterService()
    return get_tunnel_adapter_service._instance
