"""Domain models for host bootstrapping and deployment."""

from datetime import datetime
from enum import StrEnum, auto
from typing import Any, Optional
from pydantic import BaseModel, Field

class DeploymentProvider(StrEnum):
    """Supported cloud providers."""
    RAILWAY = "railway"
    RENDER = "render"
    FLY_IO = "fly_io"
    DOCKER_VPS = "docker_vps"

class DeploymentTarget(BaseModel):
    """Metadata about a deployment environment on a provider."""
    provider: DeploymentProvider
    app_name: str
    region: Optional[str] = None
    target_url: Optional[str] = None

class DeploymentEnvironmentSpec(BaseModel):
    """Specification for environment variables."""
    key: str
    description: str
    required: bool = True
    is_secret: bool = False
    default_value: Optional[str] = None
    forbidden: bool = False # If True, must NEVER be uploaded to this provider

class DeploymentArtifact(BaseModel):
    """File generated for a deployment."""
    name: str # e.g. "railway.json"
    content: str
    path: str # Relative path in the build directory
    is_sensitive: bool = False

class DeploymentPlan(BaseModel):
    """A set of instructions and artifacts for a deployment."""
    plan_id: str
    provider: DeploymentProvider
    app_name: str
    runtime: str = "python"
    start_command: str
    health_check_path: str = "/health"
    environment_variables: list[DeploymentEnvironmentSpec] = []
    artifacts: list[DeploymentArtifact] = []
    manual_steps: list[str] = []
    warnings: list[str] = []
    created_at: datetime = Field(default_factory=datetime.now)

class DeploymentReceipt(BaseModel):
    """Evidence of a completed deployment."""
    plan_id: str
    provider: DeploymentProvider
    app_name: str
    deployed_at: datetime = Field(default_factory=datetime.now)
    status: str = "success"
    logs_url: Optional[str] = None
    deployment_url: Optional[str] = None
    artifacts_snapshot: list[str] = [] # Names of artifacts used
