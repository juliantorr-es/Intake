"""Railway deployment adapter."""

import json
import uuid
from typing import Any
from intake.deploy.adapters.base import BaseDeploymentAdapter
from intake.deploy.models import (
    DeploymentPlan, 
    DeploymentArtifact, 
    DeploymentProvider, 
    DeploymentEnvironmentSpec
)

class RailwayDeploymentAdapter(BaseDeploymentAdapter):
    """Adapter for Railway.app deployment."""
    
    @property
    def provider(self) -> DeploymentProvider:
        return DeploymentProvider.RAILWAY
    
    def plan_deployment(self, app_name: str, config: dict[str, Any]) -> DeploymentPlan:
        plan_id = str(uuid.uuid4())[:8]
        
        # Define required environment variables
        env_vars = [
            DeploymentEnvironmentSpec(key="INTAKE_ENV", description="Deployment environment (e.g. production)", default_value="production"),
            DeploymentEnvironmentSpec(key="INTAKE_BASE_URL", description="Public URL of the app"),
            DeploymentEnvironmentSpec(key="INTAKE_RP_ID", description="WebAuthn RP ID (domain)"),
            DeploymentEnvironmentSpec(key="INTAKE_RP_NAME", description="WebAuthn RP Name", default_value="Intake"),
            DeploymentEnvironmentSpec(key="INTAKE_ORIGIN", description="Public origin URL"),
            DeploymentEnvironmentSpec(key="INTAKE_DATABASE_URL", description="SQLAlchemy database URL"),
            DeploymentEnvironmentSpec(key="INTAKE_SESSION_SECRET", description="Secret for signing session cookies", is_secret=True),
            DeploymentEnvironmentSpec(key="INTAKE_LOCAL_SYNC_TOKEN", description="Token for sync protocol authentication", is_secret=True),
            # Forbidden keys
            DeploymentEnvironmentSpec(key="INTAKE_LOCAL_SIGNING_KEY", description="Local private signing key", forbidden=True),
            DeploymentEnvironmentSpec(key="INTAKE_DEV_ENCRYPTION_KEY", description="Dev symmetric key (risky for prod)", is_secret=True),
        ]
        
        # Filter out forbidden keys if they accidentally leaked into config
        safe_env = [v for v in env_vars if not v.forbidden]
        
        # Start command
        start_command = "uvicorn intake.app:app --host 0.0.0.0 --port ${PORT:-8000}"
        
        # Generate railway.json
        railway_config = {
            "$schema": "https://railway.app/railway.schema.json",
            "build": {
                "builder": "NIXPACKS"
            },
            "deploy": {
                "startCommand": start_command,
                "healthCheckPath": "/health",
                "restartPolicyType": "ON_FAILURE"
            }
        }
        
        # Generate .env.hosted.example
        env_example = "# Intake Hosted Backend Environment Variables\n"
        env_example += f"# Generated for plan: {plan_id}\n\n"
        for v in safe_env:
            val = v.default_value or "REDACTED" if v.is_secret else ""
            env_example += f"{v.key}={val} # {v.description}\n"
            
        artifacts = [
            DeploymentArtifact(
                name="railway.json",
                content=json.dumps(railway_config, indent=2),
                path="railway.json"
            ),
            DeploymentArtifact(
                name=".env.hosted.example",
                content=env_example,
                path=".env.hosted.example"
            )
        ]
        
        return DeploymentPlan(
            plan_id=plan_id,
            provider=self.provider,
            app_name=app_name,
            start_command=start_command,
            environment_variables=safe_env,
            artifacts=artifacts,
            manual_steps=[
                "Install Railway CLI: npm i -g @railway/cli",
                "Login: railway login",
                "Link project: railway link",
                f"Deploy artifacts from .build/intake/deploy/railway/{plan_id}/",
                "Set environment variables in Railway dashboard."
            ],
            warnings=[
                "Local private keys are NOT included in this plan.",
                "Ensure INTAKE_DATABASE_URL is set to a persistent database."
            ]
        )
        
    def verify_readiness(self) -> dict[str, Any]:
        # Placeholder for real CLI check
        return {
            "cli_installed": False,
            "authenticated": False,
            "ready": False,
            "note": "Railway CLI check not implemented in this slice."
        }
