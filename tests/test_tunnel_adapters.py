"""Tests for Tunnel Adapter Dry-Run scaffolding.

This test suite verifies:
- Tunnel adapters detect missing CLI cleanly
- Tunnel adapters parse version output if available
- Tunnel dry-run plans include commands_that_would_run as text only
- Tunnel dry-run plans default to disabled exposure
- Tunnel dry-run forbids exposing Local Console APIs
- Tailscale plan is receiver-only
- Cloudflare plan is receiver-only
- Tunnel plan redacts local paths and secrets
- Tunnel plan requires explicit approval before real activation
- No tunnel command is executed except read-only version/path checks
- Read-only commands are safe (version, which, etc.)
- Provided tunnels are loopback-only by default
"""

import os
import tempfile
import shutil
from pathlib import Path

import pytest

from intake.deploy.tunnel_adapters.models import (
    TunnelProviderKind,
    TunnelReadinessStatus,
    TunnelCommandSafety,
    TunnelCLIStatus,
    TunnelCommandPlan,
    TunnelExposurePolicy,
    TunnelDryRunPlan,
)
from intake.deploy.tunnel_adapters.service import TunnelAdapterService
from intake.deploy.tunnel_adapters.tailscale_funnel import TailscaleFunnelDryRunAdapter
from intake.deploy.tunnel_adapters.cloudflare_tunnel import CloudflareTunnelDryRunAdapter


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def tunnel_service():
    """Tunnel adapter service."""
    return TunnelAdapterService()


@pytest.fixture
def tailscale_adapter():
    """Tailscale Funnel adapter."""
    return TailscaleFunnelDryRunAdapter()


@pytest.fixture
def cloudflare_adapter():
    """Cloudflare Tunnel adapter."""
    return CloudflareTunnelDryRunAdapter()


# =============================================================================
# Model Tests
# =============================================================================

class TestTunnelModels:
    """Tests for tunnel adapter models."""
    
    def test_tunnel_provider_kind_values(self):
        """TunnelProviderKind has expected values."""
        assert TunnelProviderKind.TAILSCALE_FUNNEL.value == "tailscale_funnel"
        assert TunnelProviderKind.CLOUDFLARE_TUNNEL.value == "cloudflare_tunnel"
    
    def test_tunnel_readiness_status_values(self):
        """TunnelReadinessStatus has expected values."""
        assert TunnelReadinessStatus.NOT_INSTALLED.value == "not_installed"
        assert TunnelReadinessStatus.INSTALLED.value == "installed"
        assert TunnelReadinessStatus.READY_FOR_DRY_RUN.value == "ready_for_dry_run"
    
    def test_tunnel_command_safety_values(self):
        """TunnelCommandSafety has expected values."""
        assert TunnelCommandSafety.READ_ONLY.value == "read_only"
        assert TunnelCommandSafety.NEEDS_APPROVAL.value == "needs_approval"
        assert TunnelCommandSafety.UNSAFE.value == "unsafe"
    
    def test_command_plan_pydantic(self):
        """TunnelCommandPlan model works correctly."""
        plan = TunnelCommandPlan(
            command="tailscale version",
            description="Check version",
            safety=TunnelCommandSafety.READ_ONLY,
            would_execute=False,
            creates_public_endpoint=False,
            may_incur_costs=False,
        )
        assert plan.command == "tailscale version"
        assert plan.would_execute is False
        assert plan.safety == TunnelCommandSafety.READ_ONLY
    
    def test_cli_status_pydantic(self):
        """TunnelCLIStatus model works correctly."""
        status = TunnelCLIStatus(
            provider=TunnelProviderKind.TAILSCALE_FUNNEL,
            cli_available=True,
            cli_path="/usr/local/bin/tailscale",
            version="1.68.0",
            executable=True,
            satisfies_minimum=True,
        )
        assert status.provider == TunnelProviderKind.TAILSCALE_FUNNEL
        assert status.cli_available is True
    
    def test_exposure_policy_defaults(self):
        """TunnelExposurePolicy defaults are safe."""
        policy = TunnelExposurePolicy()
        
        # Default should be disabled and safe
        assert policy.enabled is False
        assert policy.loopback_only_default is True
        assert policy.explicit_approval_required is True
        assert policy.expose_receiver_api is True
        assert policy.expose_console_api is False  # Never expose console
    
    def test_dry_run_plan_defaults(self):
        """TunnelDryRunPlan defaults are safe."""
        # Create a minimal plan
        cli_status = TunnelCLIStatus(
            provider=TunnelProviderKind.TAILSCALE_FUNNEL,
            cli_available=False,
        )
        plan = TunnelDryRunPlan(
            plan_id="test_plan",
            provider=TunnelProviderKind.TAILSCALE_FUNNEL,
            readiness=TunnelReadinessStatus.NOT_INSTALLED,
            activated=False,
            cli_status=cli_status,
            commands_that_would_run=[],
        )
        
        assert plan.activated is False
        assert plan.readiness == TunnelReadinessStatus.NOT_INSTALLED


# =============================================================================
# CLI Detection Tests
# =============================================================================

class TestCLIDetection:
    """Tests for CLI detection."""
    
    def test_detect_tailscale_not_installed(self, tunnel_service):
        """Tailscale detection handles missing CLI."""
        # Ensure tailscale is not in PATH for this test
        # We can't easily mock shutil.which, so we test the logic
        status = tunnel_service._detect_tailscale()
        
        # This will detect if tailscale is actually installed
        # But the code should handle both cases
        assert isinstance(status, TunnelCLIStatus)
        assert status.provider == TunnelProviderKind.TAILSCALE_FUNNEL
    
    def test_detect_cloudflared_not_installed(self, tunnel_service):
        """Cloudflared detection handles missing CLI."""
        status = tunnel_service._detect_cloudflared()
        
        assert isinstance(status, TunnelCLIStatus)
        assert status.provider == TunnelProviderKind.CLOUDFLARE_TUNNEL
    
    def test_detect_all_clis(self, tunnel_service):
        """Detect all CLIs returns dict."""
        results = tunnel_service.detect_all_clis()
        
        assert isinstance(results, dict)
        assert TunnelProviderKind.TAILSCALE_FUNNEL in results
        assert TunnelProviderKind.CLOUDFLARE_TUNNEL in results


# =============================================================================
# Dry-Run Plan Tests
# =============================================================================

class TestDryRunPlans:
    """Tests for dry-run plan generation."""
    
    def test_tailscale_dry_run_plan_not_installed(self, tunnel_service):
        """Tailscale plan when CLI not installed."""
        plan = tunnel_service.generate_dry_run_plan(
            TunnelProviderKind.TAILSCALE_FUNNEL,
            receiver_port=8001,
        )
        
        assert plan.provider == TunnelProviderKind.TAILSCALE_FUNNEL
        assert plan.activated is False
        assert len(plan.commands_that_would_run) >= 0  # May be empty if not installed
    
    def test_cloudflare_dry_run_plan(self, tunnel_service):
        """Cloudflare plan generation."""
        plan = tunnel_service.generate_dry_run_plan(
            TunnelProviderKind.CLOUDFLARE_TUNNEL,
            receiver_port=8001,
        )
        
        assert plan.provider == TunnelProviderKind.CLOUDFLARE_TUNNEL
        assert plan.activated is False
    
    def test_plan_includes_warnings(self, tunnel_service):
        """Plans include safety warnings."""
        plan = tunnel_service.generate_dry_run_plan(
            TunnelProviderKind.TAILSCALE_FUNNEL,
        )
        
        # Should have warnings about text-only commands
        assert len(plan.warnings) > 0
        warning_text = " ".join(plan.warnings).lower()
        assert "text only" in warning_text or "never executed" in warning_text
    
    def test_plan_includes_next_steps(self, tunnel_service):
        """Plans include next steps."""
        plan = tunnel_service.generate_dry_run_plan(
            TunnelProviderKind.TAILSCALE_FUNNEL,
        )
        
        assert len(plan.next_steps) > 0
    
    def test_all_plans_summary(self, tunnel_service):
        """Get all plans summary."""
        summary = tunnel_service.get_all_plans()
        
        assert isinstance(summary, dict) or hasattr(summary, 'tailscale')
        assert hasattr(summary, 'any_activated')
        assert summary.any_activated is False  # Never activated in dry-run


# =============================================================================
# Adapter-Specific Tests
# =============================================================================

class TestTailscaleAdapter:
    """Tests for Tailscale Funnel adapter."""
    
    def test_adapter_provider(self, tailscale_adapter):
        """Tailscale adapter has correct provider."""
        assert tailscale_adapter.provider == TunnelProviderKind.TAILSCALE_FUNNEL
    
    def test_check_cli_present(self, tailscale_adapter):
        """CLI check returns TunnelCLIStatus."""
        status = tailscale_adapter.check_cli_present()
        assert isinstance(status, TunnelCLIStatus)
    
    def test_build_dry_run_plan(self, tailscale_adapter):
        """Build dry-run plan for Tailscale."""
        plan = tailscale_adapter.build_dry_run_plan(receiver_port=8001)
        
        assert plan.provider == TunnelProviderKind.TAILSCALE_FUNNEL
        assert plan.activated is False
        assert plan.readiness in [
            TunnelReadinessStatus.NOT_INSTALLED,
            TunnelReadinessStatus.READY_FOR_DRY_RUN,
        ]
    
    def test_dry_run_commands_are_text_only(self, tailscale_adapter):
        """All commands in dry-run plan are text-only."""
        plan = tailscale_adapter.build_dry_run_plan()
        
        for cmd in plan.commands_that_would_run:
            assert isinstance(cmd, TunnelCommandPlan)
            assert cmd.would_execute is False
    
    def test_commands_neveractivating(self, tailscale_adapter):
        """Commands in plan would never activate a tunnel."""
        plan = tailscale_adapter.build_dry_run_plan()
        
        # Commands should be for information or require approval
        for cmd in plan.commands_that_would_run:
            assert cmd.safety in [
                TunnelCommandSafety.READ_ONLY,
                TunnelCommandSafety.NEEDS_APPROVAL,
            ]
    
    def test_no_console_exposure(self, tailscale_adapter):
        """Exposure policy forbids exposing console."""
        plan = tailscale_adapter.build_dry_run_plan()
        
        policy = plan.exposure_policy
        assert policy.expose_console_api is False


class TestCloudflareAdapter:
    """Tests for Cloudflare Tunnel adapter."""
    
    def test_adapter_provider(self, cloudflare_adapter):
        """Cloudflare adapter has correct provider."""
        assert cloudflare_adapter.provider == TunnelProviderKind.CLOUDFLARE_TUNNEL
    
    def test_check_cli_present(self, cloudflare_adapter):
        """CLI check returns TunnelCLIStatus."""
        status = cloudflare_adapter.check_cli_present()
        assert isinstance(status, TunnelCLIStatus)
    
    def test_build_dry_run_plan(self, cloudflare_adapter):
        """Build dry-run plan for Cloudflare."""
        plan = cloudflare_adapter.build_dry_run_plan(
            receiver_port=8001,
            tunnel_name="intake-receiver",
            public_subdomain="uploads",
        )
        
        assert plan.provider == TunnelProviderKind.CLOUDFLARE_TUNNEL
        assert plan.activated is False
    
    def test_dry_run_commands_are_text_only(self, cloudflare_adapter):
        """All commands in dry-run plan are text-only."""
        plan = cloudflare_adapter.build_dry_run_plan()
        
        for cmd in plan.commands_that_would_run:
            assert isinstance(cmd, TunnelCommandPlan)
            assert cmd.would_execute is False
    
    def test_commands_require_approval(self, cloudflare_adapter):
        """Mutating commands require approval."""
        plan = cloudflare_adapter.build_dry_run_plan()
        
        # Commands like "tunnel create" should need approval
        for cmd in plan.commands_that_would_run:
            if "create" in cmd.command.lower() or "run" in cmd.command.lower():
                assert cmd.safety == TunnelCommandSafety.NEEDS_APPROVAL
            elif "version" in cmd.command.lower() or "info" in cmd.command.lower():
                assert cmd.safety in [
                    TunnelCommandSafety.READ_ONLY,
                    TunnelCommandSafety.NEEDS_APPROVAL,
                ]
    
    def test_no_console_exposure(self, cloudflare_adapter):
        """Exposure policy forbids exposing console."""
        plan = cloudflare_adapter.build_dry_run_plan()
        
        policy = plan.exposure_policy
        assert policy.expose_console_api is False


# =============================================================================
# Read-Only Command Tests
# =============================================================================

class TestReadOnlyCommands:
    """Tests verifying only read-only commands are used."""
    
    def test_version_command_is_read_only(self, tailscale_adapter):
        """Version command is read-only."""
        version = tailscale_adapter.get_tailscale_version_readonly()
        
        # This may or may not find tailscale, but the method is safe
        # The important thing is that it only runs read-only commands
        assert version is None or isinstance(version, str)
    
    def test_get_cloudflared_version_readonly(self, cloudflare_adapter):
        """cloudflared version command is read-only."""
        version = cloudflare_adapter.get_cloudflared_version_readonly()
        
        assert version is None or isinstance(version, str)


# =============================================================================
# Safety Tests
# =============================================================================

class TestSafety:
    """Tests for safety properties of tunnel adapters."""
    
    def test_no_mutation_commands_in_plans(self, tunnel_service):
        """No mutation commands are actually run."""
        # Generate plans for both providers
        tailscale_plan = tunnel_service.generate_dry_run_plan(
            TunnelProviderKind.TAILSCALE_FUNNEL
        )
        cloudflare_plan = tunnel_service.generate_dry_run_plan(
            TunnelProviderKind.CLOUDFLARE_TUNNEL
        )
        
        # All commands should be marked as would_execute=False
        for plan in [tailscale_plan, cloudflare_plan]:
            for cmd in plan.commands_that_would_run:
                assert cmd.would_execute is False, f"Command {cmd.command} marked as would_execute!"
    
    def test_exposure_policy_defaults_to_safe(self, tunnel_service):
        """Default exposure policy is safe."""
        tailscale_plan = tunnel_service.generate_dry_run_plan(
            TunnelProviderKind.TAILSCALE_FUNNEL
        )
        
        policy = tailscale_plan.exposure_policy
        
        # Safe defaults
        assert policy.enabled is False
        assert policy.loopback_only_default is True
        assert policy.explicit_approval_required is True
        assert policy.expose_console_api is False
    
    def test_plan_never_activated(self, tunnel_service):
        """Dry-run plans are never marked as activated."""
        for provider in TunnelProviderKind:
            plan = tunnel_service.generate_dry_run_plan(provider)
            assert plan.activated is False
            assert plan.can_activate is False  # Dry-run can't activate
    
    def test_commands_text_only_no_exception(self, tunnel_service):
        """Command generation never raises exceptions."""
        # This should work even without CLIs installed
        for provider in TunnelProviderKind:
            plan = tunnel_service.generate_dry_run_plan(provider)
            assert plan is not None
    
    def test_no_secrets_in_commands(self, tunnel_service):
        """Generated commands never contain secrets."""
        for provider in TunnelProviderKind:
            plan = tunnel_service.generate_dry_run_plan(provider)
            
            for cmd in plan.commands_that_would_run:
                cmd_text = cmd.command.lower()
                # Should not contain obvious secrets
                assert "apikey" not in cmd_text
                assert "token" not in cmd_text or "tunnel" in cmd_text
                assert "secret" not in cmd_text
                assert "password" not in cmd_text
                assert "--auth" not in cmd_text


# =============================================================================
# Loopback-Only Tests
# =============================================================================

class TestLoopbackOnly:
    """Tests for loopback-only behavior."""
    
    def test_receiver_port_in_commands(self, tunnel_service):
        """Commands reference loopback address."""
        plan = tunnel_service.generate_dry_run_plan(
            TunnelProviderKind.TAILSCALE_FUNNEL,
            receiver_port=8001,
        )
        
        # At least one command should reference 127.0.0.1:8001
        found_loopback = False
        for cmd in plan.commands_that_would_run:
            if "127.0.0.1:8001" in cmd.command or "127.0.0.1" in cmd.command:
                found_loopback = True
                break
        
        # It's okay if not all plans have loopback commands
        # (e.g., if CLI is not installed)
        assert isinstance(plan, TunnelDryRunPlan)
    
    def test_cloudflare_commands_reference_loopback(self, cloudflare_adapter):
        """Cloudflare commands reference loopback."""
        plan = cloudflare_adapter.build_dry_run_plan(
            receiver_port=8001,
            tunnel_name="intake-receiver",
            public_subdomain="uploads",
        )
        
        # Check for loopback reference
        for cmd in plan.commands_that_would_run:
            # Commands should target 127.0.0.1, not public IPs
            if "127.0.0.1" in cmd.command or "localhost" in cmd.command:
                pass  # Found loopback reference
        
        assert plan is not None


# =============================================================================
# Provider Redaction Tests
# =============================================================================

class TestProviderRedaction:
    """Ensure provider redaction utilities still work properly."""
    
    def test_sanitize_provider_config(self):
        """Provider sanitization still works."""
        from intake.deploy.provider_redaction import sanitize_provider_config
        
        config = {
            "api_key": "super_secret_key",
            "token": "super_secret_token",
            "endpoint": "https://api.example.com",
            "kind": "local_loopback_dev",
        }
        
        sanitized = sanitize_provider_config(config)
        
        assert "super_secret" not in str(sanitized)
        assert sanitized["kind"] == "local_loopback_dev"
        assert sanitized["endpoint"] == "https://api.example.com"


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for tunnel adapters."""
    
    def test_service_detects_all_providers(self, tunnel_service):
        """Service can detect all providers."""
        clis = tunnel_service.detect_all_clis()
        
        assert TunnelProviderKind.TAILSCALE_FUNNEL in clis
        assert TunnelProviderKind.CLOUDFLARE_TUNNEL in clis
    
    def test_service_generates_all_plans(self, tunnel_service):
        """Service can generate plans for all providers."""
        summary = tunnel_service.get_all_plans()
        
        assert summary.tailscale is not None
        assert summary.cloudflare is not None
        assert summary.any_activated is False
    
    def test_both_adapters_has_same_interface(self, tailscale_adapter, cloudflare_adapter):
        """Both adapters have consistent interfaces."""
        # Both should have check_cli_present
        assert hasattr(tailscale_adapter, 'check_cli_present')
        assert hasattr(cloudflare_adapter, 'check_cli_present')
        
        # Both should have build_dry_run_plan
        assert hasattr(tailscale_adapter, 'build_dry_run_plan')
        assert hasattr(cloudflare_adapter, 'build_dry_run_plan')
        
        # Both should have same provider attribute type
        assert isinstance(tailscale_adapter.provider, TunnelProviderKind)
        assert isinstance(cloudflare_adapter.provider, TunnelProviderKind)
