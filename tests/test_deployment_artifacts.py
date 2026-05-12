"""Tests for deployment artifact generation and security constraints."""

import os
import shutil
import pytest
from intake.deploy.models import DeploymentProvider, DeploymentPlan
from intake.deploy.registry import get_adapter

@pytest.fixture
def build_dir(tmp_path):
    """Temporary build directory for artifacts."""
    d = tmp_path / ".build" / "intake" / "deploy"
    d.mkdir(parents=True, exist_ok=True)
    return str(d)

def test_railway_artifact_generation(build_dir):
    adapter = get_adapter(DeploymentProvider.RAILWAY)
    plan = adapter.plan_deployment(app_name="intake-test", config={})
    
    written_paths = adapter.write_artifacts(plan, build_dir)
    
    assert len(written_paths) == 2
    assert any(p.endswith("railway.json") for p in written_paths)
    assert any(p.endswith(".env.hosted.example") for p in written_paths)
    
    # Verify railway.json content
    railway_json_path = next(p for p in written_paths if p.endswith("railway.json"))
    with open(railway_json_path, "r") as f:
        content = f.read()
        assert "uvicorn intake.app:app" in content
        assert "${PORT:-8000}" in content
        assert "NIXPACKS" in content

def test_security_constraints_private_keys(build_dir):
    """Verify that private keys are excluded from the plan and artifacts."""
    adapter = get_adapter(DeploymentProvider.RAILWAY)
    
    # Even if we "leak" them into config (mocking potential dev error)
    config = {
        "INTAKE_LOCAL_SIGNING_KEY": "secret-signing-key",
        "INTAKE_LOCAL_PRIVATE_DECRYPT_KEY": "secret-decrypt-key"
    }
    
    plan = adapter.plan_deployment(app_name="intake-test", config=config)
    
    # 1. Check environment variables in plan
    env_keys = [v.key for v in plan.environment_variables]
    assert "INTAKE_LOCAL_SIGNING_KEY" not in env_keys
    
    # 2. Check generated artifacts for secrets
    written_paths = adapter.write_artifacts(plan, build_dir)
    env_example_path = next(p for p in written_paths if p.endswith(".env.hosted.example"))
    
    with open(env_example_path, "r") as f:
        content = f.read()
        assert "INTAKE_LOCAL_SIGNING_KEY" not in content
        assert "secret-signing-key" not in content
        assert "secret-decrypt-key" not in content
        
        # Check that expected secrets are redacted
        assert "INTAKE_SESSION_SECRET=REDACTED" in content
        assert "INTAKE_LOCAL_SYNC_TOKEN=REDACTED" in content

def test_unsupported_provider():
    with pytest.raises(ValueError, match="Unsupported deployment provider"):
        get_adapter("unknown_provider")

def test_deployment_plan_id_uniqueness():
    adapter = get_adapter(DeploymentProvider.RAILWAY)
    plan1 = adapter.plan_deployment("app1", {})
    plan2 = adapter.plan_deployment("app1", {})
    assert plan1.plan_id != plan2.plan_id
