"""Tunnel adapter dry-run scaffolding for Intake Local Receiver.

This module provides read-only CLI detection and dry-run planning for tunnel
providers. No tunnel commands are executed - only CLI detection and command
generation as text.

Tunnel adapters are for future public exposure of the Local Receiver.
The Local Receiver remains loopback-only by default.
"""

from intake.deploy.tunnel_adapters.models import (
    TunnelProviderKind,
    TunnelAdapterCapability,
    TunnelDryRunPlan,
    TunnelCommandPlan,
    TunnelExposurePolicy,
    TunnelReadinessStatus,
    TunnelCLIStatus,
    TunnelCommandSafety,
)
from intake.deploy.tunnel_adapters.tailscale_funnel import TailscaleFunnelDryRunAdapter
from intake.deploy.tunnel_adapters.cloudflare_tunnel import CloudflareTunnelDryRunAdapter
from intake.deploy.tunnel_adapters.service import TunnelAdapterService

__all__ = [
    # Models
    "TunnelProviderKind",
    "TunnelAdapterCapability",
    "TunnelDryRunPlan",
    "TunnelCommandPlan",
    "TunnelExposurePolicy",
    "TunnelReadinessStatus",
    "TunnelCLIStatus",
    "TunnelCommandSafety",
    # Adapters
    "TailscaleFunnelDryRunAdapter",
    "CloudflareTunnelDryRunAdapter",
    # Service
    "TunnelAdapterService",
]
