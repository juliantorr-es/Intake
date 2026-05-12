"""Base class for deployment adapters."""

import abc
import os
from pathlib import Path
from typing import Any
from intake.deploy.models import DeploymentPlan, DeploymentArtifact, DeploymentProvider

class BaseDeploymentAdapter(abc.ABC):
    """Abstract base class for all deployment providers."""
    
    @property
    @abc.abstractmethod
    def provider(self) -> DeploymentProvider:
        """The provider this adapter handles."""
        pass
    
    @abc.abstractmethod
    def plan_deployment(self, app_name: str, config: dict[str, Any]) -> DeploymentPlan:
        """Create a deployment plan with required artifacts and settings."""
        pass

    def write_artifacts(self, plan: DeploymentPlan, base_build_dir: str) -> list[str]:
        """Write all plan artifacts to the specified build directory.
        
        Returns a list of absolute paths to written files.
        """
        provider_dir = Path(base_build_dir) / self.provider.value / plan.plan_id
        os.makedirs(provider_dir, exist_ok=True)
        
        written_paths = []
        for artifact in plan.artifacts:
            file_path = provider_dir / artifact.path
            # Ensure subdirectories exist
            os.makedirs(file_path.parent, exist_ok=True)
            
            with open(file_path, "w") as f:
                f.write(artifact.content)
            
            written_paths.append(str(file_path.absolute()))
            
        return written_paths

    @abc.abstractmethod
    def verify_readiness(self) -> dict[str, Any]:
        """Verify if the local machine is ready to deploy to this provider.
        
        Should check for CLI presence, authentication, etc.
        """
        pass
