"""Tailscale Funnel Dry-Run Adapter.

Tailscale Funnel can expose a local service to the public internet over HTTPS.

This adapter:
- Detects if tailscale CLI is installed (read-only)
- Detects tailscale version (read-only)
- Generates dry-run plans with TEXT-ONLY commands
- NEVER executes tunnel commands
- NEVER exposes services publicly

Reference: https://tailscale.com/kb/tailscale-funnel/
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
class TailscaleFunnelConfig:
    """Configuration for Tailscale Funnel adapter."""
    receiver_port: int = 8001
    public_port: int = 443
    enabled: bool = False
    explicit_approval_required: bool = True


class TailscaleFunnelDryRunAdapter:
    """Dry-run adapter for Tailscale Funnel.
    
    Tailscale Funnel exposes a local HTTP server on the internet via Tailscale's
    proxy network. The local service gets a public https://<funnel-id>.ts.net URL.
    
    This adapter NEVER:
    - Runs `tailscale up`
    - Runs `tailscale funnel`
    - Creates public endpoints
    - Exposes the Local Console
    
    See: https://tailscale.com/kb/tailscale-funnel/
    """
    
    provider = TunnelProviderKind.TAILSCALE_FUNNEL
    
    def __init__(self, config: Optional[TailscaleFunnelConfig] = None):
        self.config = config or TailscaleFunnelConfig()
    
    def check_cli_present(self) -> TunnelCLIStatus:
        """Check if tailscale CLI is present and accessible.
        
        Uses read-only checks only:
        - shutil.which() to find in PATH
        - subprocess.run() with capture_output to get version
        """
        path = shutil.which("tailscale")
        
        if not path:
            return TunnelCLIStatus(
                provider=self.provider,
                cli_available=False,
                error="tailscale not found in PATH",
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
        """Get tailscale version (read-only command)."""
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
            logger.debug("tailscale version command timed out")
        except Exception:
            pass
        return None
    
    def _get_status(self) -> Optional[str]:
        """Get tailscale status (read-only command)."""
        path = shutil.which("tailscale")
        if not path:
            return None
        
        try:
            result = subprocess.run(
                [path, "status"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except subprocess.TimeoutExpired:
            logger.debug("tailscale status command timed out")
        except Exception:
            pass
        return None
    
    def build_dry_run_plan(self, receiver_port: Optional[int] = None) -> TunnelDryRunPlan:
        """Build a dry-run plan for Tailscale Funnel.
        
        The plan includes commands that would be run as TEXT ONLY.
        No commands are executed.
        
        Args:
            receiver_port: Port to expose (default: from config)
            
        Returns:
            Dry-run plan with text-only commands
        """
        import secrets
        
        actual_port = receiver_port or self.config.receiver_port
        plan_id = f"tailscale_funnel_dry_run_{secrets.token_hex(4)}"
        
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
                blocking_issues=["tailscale CLI not installed"],
                warnings=[
                    "Tailscale Funnel requires tailscale CLI to be installed",
                    "Commands are TEXT ONLY - NEVER EXECUTED",
                ],
                next_steps=["Install tailscale from https://tailscale.com/download"],
            )
        
        # Generate text-only commands
        commands = self._generate_text_commands(actual_port)
        
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
            ),
            can_activate=False,  # Dry-run only - never activates
            blocking_issues=[],
            warnings=[
                "TEXT ONLY - NEVER EXECUTED",
                "Tailscale Funnel would expose receiver to public internet",
                "Receiver would remain loopback-only without explicit configuration",
                "Local Console APIs would NOT be exposed",
            ],
            next_steps=[
                "Review commands that would run",
                "Ensure receiver is configured and tested locally",
                "Explicit approval required for real activation",
            ],
        )
    
    def _generate_text_commands(self, port: int) -> list[TunnelCommandPlan]:
        """Generate text-only commands for Tailscale Funnel.
        
        These are EXAMPLES ONLY. Never executed by this adapter.
        """
        return [
            TunnelCommandPlan(
                command="tailscale up",
                description="Start Tailscale connection (if not already running)",
                safety=TunnelCommandSafety.NEEDS_APPROVAL,
                would_execute=False,
                creates_public_endpoint=False,
                may_incur_costs=False,
            ),
            TunnelCommandPlan(
                command=f"tailscale funnel 127.0.0.1:{port}",
                description=f"Expose local receiver (127.0.0.1:{port}) via Funnel",
                safety=TunnelCommandSafety.NEEDS_APPROVAL,
                would_execute=False,
                creates_public_endpoint=True,
                may_incur_costs=False,
            ),
            TunnelCommandPlan(
                command="tailscale funnel status",
                description="Show Funnel status and URLs",
                safety=TunnelCommandSafety.READ_ONLY,
                would_execute=False,
                creates_public_endpoint=False,
                may_incur_costs=False,
            ),
            TunnelCommandPlan(
                command="tailscale status",
                description="Show Tailscale connection status",
                safety=TunnelCommandSafety.READ_ONLY,
                would_execute=False,
                creates_public_endpoint=False,
                may_incur_costs=False,
            ),
            TunnelCommandPlan(
                command="tailscale version",
                description="Show Tailscale version",
                safety=TunnelCommandSafety.READ_ONLY,
                would_execute=False,
                creates_public_endpoint=False,
                may_incur_costs=False,
            ),
        ]
    
    # =========================================================================
    # Alternate read-only version detection
    # =========================================================================
    
    @classmethod
    def get_tailscale_version_readonly(cls) -> Optional[str]:
        """Get tailscale version using read-only methods.
        
        Uses:
        - which to find path
        - subprocess.run with capture_output for version
        """
        path = shutil.which("tailscale")
        if not path:
            return None
        
        try:
            result = subprocess.run(
                [path, "version"],
                capture_output=True,
                text=True,
                timeout=5,
                # Ensure no shell injection
                shell=False,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None
