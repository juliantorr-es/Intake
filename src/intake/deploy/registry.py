"""Registry for deployment adapters."""

from intake.deploy.models import DeploymentProvider
from intake.deploy.adapters.base import BaseDeploymentAdapter
from intake.deploy.adapters.railway import RailwayDeploymentAdapter
from intake.deploy.adapters.render import RenderDeploymentAdapter
from intake.deploy.adapters.fly import FlyIoDeploymentAdapter

def get_adapter(provider: DeploymentProvider) -> BaseDeploymentAdapter:
    """Get the adapter for a specific provider."""
    if provider == DeploymentProvider.RAILWAY:
        return RailwayDeploymentAdapter()
    elif provider == DeploymentProvider.RENDER:
        return RenderDeploymentAdapter()
    elif provider == DeploymentProvider.FLY_IO:
        return FlyIoDeploymentAdapter()
    else:
        raise ValueError(f"Unsupported deployment provider: {provider}")

def list_supported_providers() -> list[DeploymentProvider]:
    """List all supported providers."""
    return [DeploymentProvider.RAILWAY, DeploymentProvider.RENDER, DeploymentProvider.FLY_IO]
