"""Fly.io deployment adapter stub."""

from typing import Any
from intake.deploy.adapters.base import BaseDeploymentAdapter
from intake.deploy.models import DeploymentPlan, DeploymentProvider

class FlyIoDeploymentAdapter(BaseDeploymentAdapter):
    """Adapter for Fly.io deployment (stub)."""
    
    @property
    def provider(self) -> DeploymentProvider:
        return DeploymentProvider.FLY_IO
    
    def plan_deployment(self, app_name: str, config: dict[str, Any]) -> DeploymentPlan:
        raise NotImplementedError("Fly.io deployment planning is not yet fully implemented.")
        
    def verify_readiness(self) -> dict[str, Any]:
        return {
            "ready": False,
            "note": "Fly.io adapter is a stub."
        }
