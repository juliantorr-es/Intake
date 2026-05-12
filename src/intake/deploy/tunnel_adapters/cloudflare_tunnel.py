"""Cloudflare Tunnel Dry-Run Adapter.

Cloudflare Tunnel (via cloudflared) can map a public hostname to a local service.

This adapter:
- Detects if cloudflared CLI is installed (read-only)
- Detects cloudflared version (read-only)
- Generates dry-run plans with TEXT-ONLY commands
- NEVER executes tunnel commands
- NEVER exposes services publicly
- NEVER creates real tunnels

Reference: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/
"""

import logging
import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional

from intake.deploy.tunnel_adapters.models import (
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
class CloudflareTunnelConfig:
    """Configuration for Cloudflare Tunnel adapter."""
    receiver_port: int = 8001
    tunnel_name: str = "intake-receiver"
    public_subdomain: str = "uploads"
    enabled: bool = False
    explicit_approval_required: bool = True


class CloudflareTunnelDryRunAdapter:
    """Dry-run adapter for Cloudflare Tunnel.
    
    Cloudflare Tunnel (cloudflared) creates a secure tunnel from a local
    service to Cloudflare's edge network. The tunnel can be exposed via
    a public DNS record.
    
    This adapter NEVER:
    - Runs `cloudflared tunnel create`
    - Runs `cloudflared tunnel route`
    - Runs `cloudflared tunnel run`
    - Creates public DNS records
    - Exposes the Local Console
    
    See: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/
    """
    
    provider = TunnelProviderKind.CLOUDFLARE_TUNNEL
    
    def __init__(self, config: Optional[CloudflareTunnelConfig] = None):
        self.config = config or CloudflareTunnelConfig()
    
    def check_cli_present(self) -> TunnelCLIStatus:
        """Check if cloudflared CLI is present and accessible.
        
        Uses read-only checks only:
        - shutil.which() to find in PATH
        - subprocess.run() with capture_output to get version
        """
        path = shutil.which("cloudflared")
        
        if not path:
            return TunnelCLIStatus(
                provider=self.provider,
                cli_available=False,
                error="cloudflared not found in PATH",
            )
        
        # Check executable
        try:
            import os
            is_executable = os.access(path, os.X_OK)
        except Exception:
            is_executable = False
        
        # Get version (read-only)
        version = self._get_version(path)
        
        return TunnelCLIStatus(
            provider=self.provider,
            cli_available=True,
            cli_path=path,
            version=version,
            executable=is_executable,
            satisfies_minimum=True,
        )
    
    def _get_version(self, path: str) -> Optional[str]:
        """Get cloudflared version (read-only command)."""
        try:
            result = subprocess.run(
                [path, "version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except subprocess.TimeoutExpired:
            logger.debug("cloudflared version command timed out")
        except Exception:
            pass
        return None
    
    def build_dry_run_plan(
        self,
        receiver_port: Optional[int] = None,
        tunnel_name: Optional[str] = None,
        public_subdomain: Optional[str] = None,
    ) -> TunnelDryRunPlan:
        """Build a dry-run plan for Cloudflare Tunnel.
        
        The plan includes commands that would be run as TEXT ONLY.
        No commands are executed.
        
        Args:
            receiver_port: Port to expose (default: from config)
            tunnel_name: Name for the tunnel (default: from config)
            public_subdomain: Public subdomain (default: from config)
            
        Returns:
            Dry-run plan with text-only commands
        """
        import secrets
        
        actual_port = receiver_port or self.config.receiver_port
        actual_name = tunnel_name or self.config.tunnel_name
        actual_subdomain = public_subdomain or self.config.public_subdomain
        
        plan_id = f"cloudflare_tunnel_dry_run_{secrets.token_hex(4)}"
        
        # Check CLI
        cli_status = self.check_cli_present()
        
        if not cli_status.cli_available:
            return TunnelDryRunPlan(
                plan_id=plan_id,
                provider=self.provider,
                readiness=TunnelReadinessStatus.NOT_INSTALLED,
                activated=False,
                cli_status=cli_status,
                commands_that_would_run=[],
                exposure_policy=TunnelExposurePolicy(),
                can_activate=False,
                blocking_issues=["cloudflared CLI not installed"],
                warnings=[
                    "Cloudflare Tunnel requires cloudflared CLI to be installed",
                    "Commands are TEXT ONLY - NEVER EXECUTED",
                ],
                next_steps=["Install cloudflared from https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/tunnel-guide/"],
            )
        
        # Generate text-only commands
        commands = self._generate_text_commands(
            actual_name, actual_port, actual_subdomain
        )
        
        return TunnelDryRunPlan(
            plan_id=plan_id,
            provider=self.provider,
            readiness=TunnelReadinessStatus.READY_FOR_DRY_RUN,
            activated=False,
            cli_status=cli_status,
            commands_that_would_run=commands,
            exposure_policy=TunnelExposurePolicy(
                enabled=False,
                loopback_only_default=True,
                explicit_approval_required=True,
                expose_receiver_api=True,
                expose_console_api=False,
                allowed_paths=[f"/receiver/*"],
                blocked_paths=["/", "/console/*", "/decrypt/*", "/review/*", "/api/*"],
            ),
            can_activate=False,  # Dry-run only - never activates
            blocking_issues=[],
            warnings=[
                "TEXT ONLY - NEVER EXECUTED",
                "Cloudflare Tunnel would expose receiver to public internet",
                "Receiver would remain loopback-only without explicit configuration",
                "Local Console APIs would NOT be exposed",
                "May incur costs at scale",
            ],
            next_steps=[
                "Review commands that would run",
                "Ensure receiver is configured and tested locally",
                "Set up Cloudflare account and authentication",
                "Explicit approval required for real activation",
            ],
        )
    
    def _generate_text_commands(
        self,
        tunnel_name: str,
        port: int,
        subdomain: str,
    ) -> list[TunnelCommandPlan]:
        """Generate text-only commands for Cloudflare Tunnel.
        
        These are EXAMPLES ONLY. Never executed by this adapter.
        """
        return [
            TunnelCommandPlan(
                command="cloudflared --version",
                description="Check cloudflared version",
                safety=TunnelCommandSafety.READ_ONLY,
                would_execute=False,
                creates_public_endpoint=False,
                may_incur_costs=False,
            ),
            TunnelCommandPlan(
                command=f"cloudflared tunnel info",
                description="List existing tunnels",
                safety=TunnelCommandSafety.READ_ONLY,
                would_execute=False,
                creates_public_endpoint=False,
                may_incur_costs=False,
            ),
            TunnelCommandPlan(
                command=f"cloudflared tunnel create {tunnel_name}",
                description=f"Create tunnel '{tunnel_name}'",
                safety=TunnelCommandSafety.NEEDS_APPROVAL,
                would_execute=False,
                creates_public_endpoint=False,  # Tunnel created but not yet public
                may_incur_costs=True,
            ),
            TunnelCommandPlan(
                command=f"cloudflared tunnel route dns {tunnel_name} {subdomain}",
                description=f"Map {subdomain} to tunnel '{tunnel_name}'",
                safety=TunnelCommandSafety.NEEDS_APPROVAL,
                would_execute=False,
                creates_public_endpoint=True,
                may_incur_costs=False,
            ),
            TunnelCommandPlan(
                command=f"cloudflared tunnel run --url http://127.0.0.1:{port} {tunnel_name}",
                description=f"Run tunnel '{tunnel_name}' pointing to 127.0.0.1:{port}",
                safety=TunnelCommandSafety.NEEDS_APPROVAL,
                would_execute=False,
                creates_public_endpoint=True,
                may_incur_costs=False,
            ),
            TunnelCommandPlan(
                command="cloudflared tunnel cleanup",
                description="Clean up unused tunnels",
                safety=TunnelCommandSafety.NEEDS_APPROVAL,
                would_execute=False,
                creates_public_endpoint=False,
                may_incur_costs=False,
            ),
        ]
    
    # =========================================================================
    # Alternate read-only version detection
    # =========================================================================
    
    @classmethod
    def get_cloudflared_version_readonly(cls) -> Optional[str]:
        """Get cloudflared version using read-only methods.
        
        Uses:
        - which to find path
        - subprocess.run with capture_output for version
        """
        path = shutil.which("cloudflared")
        if not path:
            return None
        
        try:
            result = subprocess.run(
                [path, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                shell=False,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None
