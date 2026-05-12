"""Local-only API for the Intake Console."""

from fastapi import APIRouter, Depends, HTTPException
from typing import Any, Optional
from pydantic import BaseModel

from intake.config import get_settings
from intake.local_console.sync_client import LocalSyncClient
from intake.local_console.review_service import LocalQuoteReviewService, LocalDecryptedQuoteReview
from intake.sync.models import HostedQuoteProjection
from intake.deploy.registry import list_supported_providers
from intake.local_console.receiver.models import ReceiverAvailabilityStatus
from intake.local_console.receiver.service import LocalReceiverService

router = APIRouter()


@router.get("/health")
async def health():
    """Simple health check endpoint."""
    return {"status": "ok"}



# Receiver service singleton
_receiver_service: Optional[LocalReceiverService] = None


def get_receiver_service() -> Optional[LocalReceiverService]:
    """Get the receiver service instance."""
    global _receiver_service
    if _receiver_service is None:
        try:
            from intake.local_console.receiver import LocalReceiverService
            _receiver_service = LocalReceiverService()
        except Exception:
            pass
    return _receiver_service


class LocalStatusResponse(BaseModel):
    """Status of the local console and its connection to hosted."""
    hosted_url: str
    sync_auth_configured: bool
    encryption_key_configured: bool
    signing_key_configured: bool
    is_loopback: bool
    # Local Secure Unlock
    local_unlock_required: bool
    local_unlock_ttl: int
    # Tunnel adapter status
    tunnel_adapter_status: Optional[str] = "not_configured"
    tailscale_funnel_status: Optional[str] = None
    cloudflare_tunnel_status: Optional[str] = None


class ProviderStatusResponse(BaseModel):
    """Status of a single provider (e.g., Railway)."""
    provider: str
    cli_present: bool
    cli_version: Optional[str] = None
    authenticated: Optional[bool] = None
    project_linked: Optional[bool] = None
    ready_status: str = "not_ready"  # "not_ready", "cli_missing", "ready_for_setup", "fully_ready"
    blocking_issues: list[str] = []


class DeployReadinessResponse(BaseModel):
    """Deployment readiness status for Local Console."""
    status: str = "dry_run_only"  # "not_configured", "dry_run_only", "ready", "deployed"
    railway: ProviderStatusResponse
    upload_receiver_configured: bool = True  # Local receiver is now configured
    upload_receiver_status: Optional[str] = "online"
    upload_receiver_loopback_only: bool = True
    fallback_storage_configured: bool = False
    # Tunnel adapter status
    tunnel_adapters_configured: bool = True
    tailscale_funnel_configured: bool = False
    cloudflare_tunnel_configured: bool = False
    tunnel_exposure_enabled: bool = False
    tunnel_loopback_only: bool = True
    recommended_next_step: str = "install_railway_cli"
    dry_run_only: bool = True


class RailwayDryRunPlanResponse(BaseModel):
    """Response containing Railway dry-run plan details."""
    plan_id: str
    railway_cli_present: bool
    railway_cli_version: Optional[str] = None
    railway_authenticated: Optional[bool] = None
    railway_project_linked: Optional[bool] = None
    blocking_issues: list[str] = []
    warnings: list[str] = []
    next_manual_steps: list[str] = []
    # Commands as text only - never executed
    example_commands: list[str] = []


@router.get("/status", response_model=LocalStatusResponse)
async def get_status():
    """Get status of the local console."""
    settings = get_settings()
    
    # Get tunnel adapter status
    tailscale_status = None
    cloudflare_status = None
    try:
        from intake.deploy.tunnel_adapters import get_tunnel_adapter_service
        tunnel_svc = get_tunnel_adapter_service()
        plans = tunnel_svc.get_all_plans()
        if plans.tailscale:
            tailscale_status = plans.tailscale.readiness.value
        if plans.cloudflare:
            cloudflare_status = plans.cloudflare.readiness.value
    except Exception:
        pass
    
    # Redact tokens/keys: only show if they exist
    return LocalStatusResponse(
        hosted_url=settings.intake_base_url,
        sync_auth_configured=bool(settings.intake_local_sync_token),
        encryption_key_configured=bool(settings.intake_dev_encryption_key),
        signing_key_configured=bool(settings.intake_local_signing_key),
        is_loopback=True,  # API should only be reachable via 127.0.0.1
        local_unlock_required=settings.intake_require_local_unlock_for_decrypt,
        local_unlock_ttl=settings.intake_local_unlock_ttl_seconds,
        tunnel_adapter_status="active",
        tailscale_funnel_status=tailscale_status,
        cloudflare_tunnel_status=cloudflare_status,
    )


def _get_railway_status() -> ProviderStatusResponse:
    """Get Railway CLI and project status."""
    try:
        # Import here to avoid issues if module is not available
        from intake.deploy.railway_dry_run import RailwayDryRunBootstrapService
        
        service = RailwayDryRunBootstrapService()
        
        # Check CLI
        cli = service.check_railway_cli()
        
        # Check auth
        auth = service.check_railway_project()
        
        # Build dry-run plan for status
        plan = service.build_dry_run_plan(include_artifacts=False)
        
        if not cli.present:
            return ProviderStatusResponse(
                provider="railway",
                cli_present=False,
                cli_version=None,
                authenticated=None,
                project_linked=None,
                ready_status="cli_missing",
                blocking_issues=["Railway CLI not installed"]
            )
        
        is_ready = plan.is_ready if auth.linked else False
        is_setup_ready = plan.can_attempt_deployment
        
        return ProviderStatusResponse(
            provider="railway",
            cli_present=True,
            cli_version=cli.version,
            authenticated=auth.linked if auth.linked else None,
            project_linked=auth.linked,
            ready_status="fully_ready" if is_ready else "ready_for_setup" if is_setup_ready else "not_ready",
            blocking_issues=plan.blocking_issues
        )
    except Exception:
        # Fallback if there are any issues
        return ProviderStatusResponse(
            provider="railway",
            cli_present=False,
            ready_status="not_ready",
            blocking_issues=["Railway check failed"]
        )


@router.get("/deploy/status", response_model=DeployReadinessResponse)
async def get_deploy_status():
    """Get deployment provider readiness status."""
    railway_status = _get_railway_status()
    
    # Get receiver status
    receiver_svc = get_receiver_service()
    if receiver_svc:
        receiver_status = receiver_svc.get_availability().status.value
    else:
        receiver_status = "not_configured"
    
    if railway_status.cli_present and railway_status.ready_status == "fully_ready":
        recommended = "review_and_deploy"
    elif railway_status.cli_present:
        recommended = "link_project"
    else:
        recommended = "install_railway_cli"
    
    # Get tunnel adapter status
    tailscale_status = None
    cloudflare_status = None
    try:
        from intake.deploy.tunnel_adapters import get_tunnel_adapter_service
        tunnel_svc = get_tunnel_adapter_service()
        plans = tunnel_svc.get_all_plans()
        if plans.tailscale:
            tailscale_status = plans.tailscale.readiness.value
        if plans.cloudflare:
            cloudflare_status = plans.cloudflare.readiness.value
    except Exception:
        pass
    
    return DeployReadinessResponse(
        status="dry_run_only",
        railway=railway_status,
        upload_receiver_configured=True,
        upload_receiver_status=receiver_status,
        upload_receiver_loopback_only=True,
        fallback_storage_configured=False,
        tunnel_adapters_configured=True,
        tailscale_funnel_configured=tailscale_status == "installed" or tailscale_status == "ready_for_dry_run",
        cloudflare_tunnel_configured=cloudflare_status == "installed" or cloudflare_status == "ready_for_dry_run",
        tunnel_exposure_enabled=False,  # Always false - tunnel activation not implemented
        tunnel_loopback_only=True,  # Tunnel adapters default to loopback-only
        recommended_next_step=recommended,
        dry_run_only=True
    )


@router.get("/receiver/status", response_model=ReceiverAvailabilityStatus)
async def get_receiver_status():
    """Get local receiver availability status."""
    receiver_svc = get_receiver_service()
    if receiver_svc:
        return receiver_svc.get_availability()
    raise HTTPException(status_code=503, detail="Receiver service not configured")


@router.get("/tunnel/status")
async def get_tunnel_status():
    """Get tunnel adapter dry-run status for all providers.
    
    Returns dry-run plans only. No tunnel commands are executed or activated.
    """
    try:
        from intake.deploy.tunnel_adapters import get_tunnel_adapter_service
        tunnel_svc = get_tunnel_adapter_service()
        return tunnel_svc.get_all_plans()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tunnel/{provider}/dry-run")
async def get_tunnel_dry_run_plan(provider: str):
    """Get dry-run plan for a specific tunnel provider.
    
    Generates TEXT-ONLY commands that would be run.
    NO commands are executed or activated.
    """
    try:
        from intake.deploy.tunnel_adapters.models import TunnelProviderKind
        from intake.deploy.tunnel_adapters import get_tunnel_adapter_service
        
        tunnel_svc = get_tunnel_adapter_service()
        
        # Validate provider
        try:
            provider_enum = TunnelProviderKind(provider)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown tunnel provider: {provider}")
        
        plan = tunnel_svc.generate_dry_run_plan(provider_enum, receiver_port=8001)
        return plan
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/deploy/railway/dry-run", response_model=RailwayDryRunPlanResponse)
async def get_railway_dry_run_plan():
    """Generate and return a Railway dry-run plan.
    
    This does NOT execute any Railway commands. It only generates
    a plan showing what would happen.
    """
    try:
        from intake.deploy.railway_dry_run import RailwayDryRunBootstrapService
        
        service = RailwayDryRunBootstrapService()
        plan = service.build_dry_run_plan(include_artifacts=False)
        
        return RailwayDryRunPlanResponse(
            plan_id=plan.plan_id,
            railway_cli_present=plan.railway_cli_present,
            railway_cli_version=plan.railway_cli_version,
            railway_authenticated=plan.railway_authenticated,
            railway_project_linked=plan.railway_project_linked,
            blocking_issues=plan.blocking_issues,
            warnings=plan.warnings,
            next_manual_steps=plan.next_manual_steps,
            example_commands=plan.commands_that_would_run[:10]  # Limit for response
        )
    except Exception as e:
        return RailwayDryRunPlanResponse(
            plan_id="error",
            railway_cli_present=False,
            warnings=[f"Dry-run plan generation failed: {str(e)}"]
        )

def get_local_review_service() -> LocalQuoteReviewService:
    """Dependency factory for the local review service."""
    return LocalQuoteReviewService()

@router.get("/quotes/pending", response_model=list[HostedQuoteProjection])
async def get_pending_quotes(
    service: LocalQuoteReviewService = Depends(get_local_review_service)
):
    """Get pending quote projections from hosted."""
    try:
        return service.get_pending_reviews()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch from hosted: {e}")

@router.get("/quotes/{quote_id}/review", response_model=LocalDecryptedQuoteReview)
async def get_quote_review(
    quote_id: str,
    service: LocalQuoteReviewService = Depends(get_local_review_service)
):
    """Fetch and decrypt a quote for local review."""
    try:
        return service.get_decrypted_review(quote_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Decryption failed: {e}")

@router.post("/quotes/{quote_id}/start-review")
async def start_quote_review(
    quote_id: str,
    service: LocalQuoteReviewService = Depends(get_local_review_service)
):
    """Transition a quote to reviewing status on hosted."""
    try:
        return service.start_review(quote_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Action failed: {e}")

@router.post("/sync/pull")
async def trigger_sync_pull():
    """Manually trigger a sync pull (placeholder for now)."""
    return {"status": "success", "message": "Sync pull triggered"}
