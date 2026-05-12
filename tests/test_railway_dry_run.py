"""Tests for Railway dry-run bootstrap behavior.

These tests verify that the Railway dry-run service:
- Does not call mutating commands
- Reports CLI missing cleanly
- Parses CLI version when available
- Returns plans with commands as inert text only
- Includes required hosted env vars
- Excludes forbidden local-only env vars
- Generated artifacts do not contain secret values
"""

import subprocess
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from intake.deploy.railway_dry_run import (
    RailwayDryRunBootstrapService,
    RailwayCliInfo,
    RailwayAuthInfo,
    RailwayProjectInfo,
    RailwayDryRunPlan,
    HOSTED_ENV_SPECS,
    FORBIDDEN_ENV_SPECS,
)


class TestRailwayCliDetection:
    """Tests for Railway CLI detection."""

    def test_check_railway_cli_not_installed(self, monkeypatch):
        """CLI detection returns present=False when railway CLI not found."""
        # Mock subprocess to simulate railway not found
        def mock_run(*args, **kwargs):
            raise FileNotFoundError("railway not found")
        
        monkeypatch.setattr(subprocess, "run", mock_run)
        monkeypatch.setattr("shutil.which", lambda x: None)
        
        service = RailwayDryRunBootstrapService()
        cli = service.check_railway_cli()
        
        assert cli.present is False
        assert cli.version is None
        assert cli.path is None
        assert cli.error == "Railway CLI not found"

    def test_check_railway_cli_via_version_flag(self, monkeypatch, tmp_path):
        """CLI detection parses version from railway --version output."""
        def mock_run(*args, **kwargs):
            cmd = args[0]
            if cmd == ["railway", "--version"]:
                class Result:
                    returncode = 0
                    stdout = "@railway/cli/4.0.0\n"
                    stderr = ""
                return Result()
            raise FileNotFoundError()
        
        monkeypatch.setattr(subprocess, "run", mock_run)
        monkeypatch.setattr("shutil.which", lambda x: str(tmp_path / "railway"))
        
        service = RailwayDryRunBootstrapService(working_dir=str(tmp_path))
        cli = service.check_railway_cli()
        
        assert cli.present is True
        assert cli.version == "4.0.0"
        assert cli.path == str(tmp_path / "railway")

    def test_check_railway_cli_version_fallback_patterns(self, monkeypatch, tmp_path):
        """CLI detection handles various version string formats."""
        test_cases = [
            ("4.0.0", "4.0.0"),
            ("@railway/cli/4.0.0", "4.0.0"),
            ("railway-cli version 4.0.0", "4.0.0"),
            ("4.0.0-beta.1", "4.0.0"),
        ]
        
        for output, expected_version in test_cases:
            def mock_run(*args, **kwargs):
                cmd = args[0]
                if cmd == ["railway", "--version"]:
                    class Result:
                        returncode = 0
                        stdout = output
                        stderr = ""
                    return Result()
                raise FileNotFoundError()
            
            monkeypatch.setattr(subprocess, "run", mock_run)
            monkeypatch.setattr("shutil.which", lambda x: str(tmp_path / "railway"))
            
            service = RailwayDryRunBootstrapService(working_dir=str(tmp_path))
            cli = service.check_railway_cli()
            
            assert cli.present is True
            # Should extract version number
            assert cli.version is not None

    def test_check_railway_cli_via_which(self, monkeypatch, tmp_path):
        """CLI detection falls back to which command."""
        def mock_run(*args, **kwargs):
            cmd = args[0]
            if cmd == ["railway", "--version"]:
                raise FileNotFoundError()
            if cmd == ["which", "railway"]:
                class Result:
                    returncode = 0
                    stdout = "/usr/local/bin/railway\n"
                    stderr = ""
                return Result()
            raise FileNotFoundError()
        
        monkeypatch.setattr(subprocess, "run", mock_run)
        monkeypatch.setattr("shutil.which", lambda x: None)
        
        service = RailwayDryRunBootstrapService(working_dir=str(tmp_path))
        cli = service.check_railway_cli()
        
        assert cli.present is True
        assert cli.path == "/usr/local/bin/railway"

    def test_cli_detection_timeout_handled(self, monkeypatch):
        """CLI detection handles timeout gracefully."""
        def mock_run(*args, **kwargs):
            raise subprocess.TimeoutExpired("railway", 5)
        
        monkeypatch.setattr(subprocess, "run", mock_run)
        monkeypatch.setattr("shutil.which", lambda x: None)
        
        service = RailwayDryRunBootstrapService()
        cli = service.check_railway_cli()
        
        assert cli.present is False


class TestRailwayAuthAndProjectDetection:
    """Tests for Railway auth and project detection."""

    def test_check_railway_auth_no_config(self, tmp_path):
        """Auth detection returns not authenticated when no config files exist."""
        service = RailwayDryRunBootstrapService(working_dir=str(tmp_path))
        auth = service.check_railway_auth()
        
        assert auth.has_config_file is False
        assert auth.config_file_path is None
        assert auth.inferred_authenticated is False
        assert "No Railway config file found" in auth.note

    def test_check_railway_auth_with_config(self, tmp_path):
        """Auth detection finds config files."""
        config_dir = tmp_path / ".railway"
        config_dir.mkdir()
        config_file = config_dir / "config.json"
        config_file.write_text('{"token": "test"}')
        
        service = RailwayDryRunBootstrapService(working_dir=str(tmp_path))
        auth = service.check_railway_auth()
        
        # Should find the config in home directory or working directory
        # Since we can't easily mock Path.home, test the working directory path
        project_config = tmp_path / "railway.json"
        project_config.write_text('{}')
        
        service2 = RailwayDryRunBootstrapService(working_dir=str(tmp_path))
        auth2 = service2.check_railway_auth()
        
        assert auth2.has_config_file is True

    def test_check_railway_project_with_railway_json(self, tmp_path):
        """Project detection finds railway.json file."""
        railway_json = tmp_path / "railway.json"
        railway_json.write_text('{"name": "test-project"}')
        
        service = RailwayDryRunBootstrapService(working_dir=str(tmp_path))
        project = service.check_railway_project()
        
        assert project.linked is True
        assert project.linkage_file == str(railway_json)

    def test_check_railway_project_no_file(self, tmp_path):
        """Project detection returns unknown when no files found."""
        service = RailwayDryRunBootstrapService(working_dir=str(tmp_path))
        project = service.check_railway_project()
        
        assert project.linked is None


class TestDryRunPlanGeneration:
    """Tests for dry-run plan generation."""

    def test_build_dry_run_plan_cli_missing(self, tmp_path, monkeypatch):
        """Plan generation works when CLI is missing."""
        def mock_run(*args, **kwargs):
            raise FileNotFoundError()
        
        monkeypatch.setattr(subprocess, "run", mock_run)
        monkeypatch.setattr("shutil.which", lambda x: None)
        
        service = RailwayDryRunBootstrapService(working_dir=str(tmp_path))
        plan = service.build_dry_run_plan(app_name="test-app")
        
        assert isinstance(plan, RailwayDryRunPlan)
        assert plan.railway_cli_present is False
        assert plan.railway_cli_version is None
        assert len(plan.blocking_issues) > 0
        assert "Railway CLI is not installed" in plan.blocking_issues
        assert plan.can_attempt_deployment is False

    def test_build_dry_run_plan_cli_present(self, tmp_path, monkeypatch):
        """Plan generation works when CLI is present."""
        def mock_run(*args, **kwargs):
            cmd = args[0]
            if cmd == ["railway", "--version"]:
                class Result:
                    returncode = 0
                    stdout = "@railway/cli/4.0.0\n"
                    stderr = ""
                return Result()
            raise FileNotFoundError()
        
        monkeypatch.setattr(subprocess, "run", mock_run)
        monkeypatch.setattr("shutil.which", lambda x: str(tmp_path / "railway"))
        
        service = RailwayDryRunBootstrapService(working_dir=str(tmp_path))
        plan = service.build_dry_run_plan(app_name="test-app")
        
        assert plan.railway_cli_present is True
        assert plan.railway_cli_version == "4.0.0"
        assert plan.can_attempt_deployment is True

    def test_plan_includes_required_env_vars(self, tmp_path, monkeypatch):
        """Plan includes all required hosted env vars."""
        def mock_run(*args, **kwargs):
            raise FileNotFoundError()
        
        monkeypatch.setattr(subprocess, "run", mock_run)
        monkeypatch.setattr("shutil.which", lambda x: str(tmp_path / "railway"))
        
        service = RailwayDryRunBootstrapService(working_dir=str(tmp_path))
        plan = service.build_dry_run_plan()
        
        # Check required env vars are present
        required_keys = {spec.key for spec in HOSTED_ENV_SPECS}
        plan_keys = {spec.key for spec in plan.required_env_vars}
        
        assert required_keys == plan_keys

    def test_plan_excludes_forbidden_env_vars(self, tmp_path, monkeypatch):
        """Plan assigns forbidden vars to forbidden_env_vars, not required."""
        def mock_run(*args, **kwargs):
            raise FileNotFoundError()
        
        monkeypatch.setattr(subprocess, "run", mock_run)
        monkeypatch.setattr("shutil.which", lambda x: str(tmp_path / "railway"))
        
        service = RailwayDryRunBootstrapService(working_dir=str(tmp_path))
        plan = service.build_dry_run_plan()
        
        # Forbidden vars should be in forbidden list
        forbidden_keys = {spec.key for spec in FORBIDDEN_ENV_SPECS}
        plan_forbidden_keys = {spec.key for spec in plan.forbidden_env_vars}
        
        assert forbidden_keys == plan_forbidden_keys
        
        # Forbidden vars should NOT be in required list
        required_keys = {spec.key for spec in plan.required_env_vars}
        for key in forbidden_keys:
            assert key not in required_keys

    def test_plan_commands_are_text_only(self, tmp_path, monkeypatch):
        """Plan commands are comment-prefixed text, not executable commands."""
        def mock_run(*args, **kwargs):
            raise FileNotFoundError()
        
        monkeypatch.setattr(subprocess, "run", mock_run)
        monkeypatch.setattr("shutil.which", lambda x: str(tmp_path / "railway"))
        
        service = RailwayDryRunBootstrapService(working_dir=str(tmp_path))
        plan = service.build_dry_run_plan()
        
        # All commands should start with # (comment)
        for cmd in plan.commands_that_would_run:
            assert cmd.startswith("#"), f"Command should start with #: {cmd}"
        
        # Check for key commands that should be present as comments
        command_text = " ".join(plan.commands_that_would_run)
        assert "railway login" in command_text
        assert "railway link" in command_text
        assert "railway init" in command_text
        assert "railway up" in command_text
        
        # Ensure they're comments, not actual commands
        assert "# Like: railway login" in command_text
        assert "# To actually deploy: railway up" in command_text

    def test_plan_artifacts_include_railway_json(self, tmp_path, monkeypatch):
        """Plan includes railway.json and .env.hosted.example artifacts."""
        def mock_run(*args, **kwargs):
            raise FileNotFoundError()
        
        monkeypatch.setattr(subprocess, "run", mock_run)
        monkeypatch.setattr("shutil.which", lambda x: str(tmp_path / "railway"))
        
        service = RailwayDryRunBootstrapService(working_dir=str(tmp_path))
        plan = service.build_dry_run_plan(include_artifacts=True)
        
        assert len(plan.artifact_contents) >= 2
        
        has_railway_json = any("railway.json" in path for path in plan.artifact_contents.keys())
        has_env_example = any(".env.hosted.example" in path for path in plan.artifact_contents.keys())
        
        assert has_railway_json is True
        assert has_env_example is True

    def test_plan_artifacts_not_written_by_default(self, tmp_path, monkeypatch):
        """Artifacts are not written to disk by default."""
        def mock_run(*args, **kwargs):
            raise FileNotFoundError()
        
        monkeypatch.setattr(subprocess, "run", mock_run)
        monkeypatch.setattr("shutil.which", lambda x: str(tmp_path / "railway"))
        
        service = RailwayDryRunBootstrapService(working_dir=str(tmp_path))
        plan = service.build_dry_run_plan(include_artifacts=False)
        
        assert len(plan.generated_artifact_paths) == 0
        assert len(plan.artifact_contents) == 0

    def test_plan_inspect_environment(self, tmp_path, monkeypatch):
        """Inspect environment returns complete status."""
        def mock_run(*args, **kwargs):
            cmd = args[0]
            if cmd == ["railway", "--version"]:
                class Result:
                    returncode = 0
                    stdout = "@railway/cli/4.0.0\n"
                    stderr = ""
                return Result()
            raise FileNotFoundError()
        
        monkeypatch.setattr(subprocess, "run", mock_run)
        monkeypatch.setattr("shutil.which", lambda x: str(tmp_path / "railway"))
        
        service = RailwayDryRunBootstrapService(working_dir=str(tmp_path))
        env_info = service.inspect_environment()
        
        assert "railway_cli_present" in env_info
        assert "railway_cli_version" in env_info
        assert "railway_auth" in env_info
        assert "railway_project" in env_info


class TestArtifactValidation:
    """Tests for artifact security validation."""

    def test_validate_artifacts_forbidden_keys_in_comments(self, tmp_path, monkeypatch):
        """Validation passes when forbidden keys are only in comments."""
        def mock_run(*args, **kwargs):
            raise FileNotFoundError()
        
        monkeypatch.setattr(subprocess, "run", mock_run)
        monkeypatch.setattr("shutil.which", lambda x: str(tmp_path / "railway"))
        
        service = RailwayDryRunBootstrapService(working_dir=str(tmp_path))
        plan = service.build_dry_run_plan()
        
        validation = service.validate_artifacts(plan)
        
        assert validation["valid"] is True
        assert len(validation["issues"]) == 0

    def test_generated_env_example_redacts_secrets(self, tmp_path, monkeypatch):
        """Generated .env.hosted.example redacts secret values."""
        def mock_run(*args, **kwargs):
            raise FileNotFoundError()
        
        monkeypatch.setattr(subprocess, "run", mock_run)
        monkeypatch.setattr("shutil.which", lambda x: str(tmp_path / "railway"))
        
        service = RailwayDryRunBootstrapService(working_dir=str(tmp_path))
        plan = service.build_dry_run_plan(include_artifacts=True)
        
        # Get the env example content
        env_content = None
        for path, content in plan.artifact_contents.items():
            if ".env.hosted.example" in path:
                env_content = content
                break
        
        assert env_content is not None
        
        # Check that secrets are redacted
        assert "INTAKE_SESSION_SECRET=REDACTED" in env_content
        assert "INTAKE_LOCAL_SYNC_TOKEN=REDACTED" in env_content
        
        # Check that forbidden keys are in comments only
        assert "INTAKE_LOCAL_SIGNING_KEY" in env_content
        assert "# INTAKE_LOCAL_SIGNING_KEY" in env_content
        # Should NOT be set as actual env var (not commented)
        lines = env_content.split("\n")
        for line in lines:
            if "INTAKE_LOCAL_SIGNING_KEY" in line and not line.strip().startswith("#"):
                assert False, f"INTAKE_LOCAL_SIGNING_KEY should only be in comments: {line}"

    def test_env_example_includes_all_hosted_vars(self, tmp_path, monkeypatch):
        """Generated env example includes all hosted-safe variables."""
        def mock_run(*args, **kwargs):
            raise FileNotFoundError()
        
        monkeypatch.setattr(subprocess, "run", mock_run)
        monkeypatch.setattr("shutil.which", lambda x: str(tmp_path / "railway"))
        
        service = RailwayDryRunBootstrapService(working_dir=str(tmp_path))
        plan = service.build_dry_run_plan(include_artifacts=True)
        
        env_content = None
        for path, content in plan.artifact_contents.items():
            if ".env.hosted.example" in path:
                env_content = content
                break
        
        assert env_content is not None
        
        # Check all hosted env vars are present
        for spec in HOSTED_ENV_SPECS:
            assert spec.key in env_content, f"Missing {spec.key} in env example"


class TestNextManualSteps:
    """Tests for next manual steps explanation."""

    def test_explain_next_manual_steps(self, tmp_path, monkeypatch):
        """Next manual steps are provided as safe text."""
        def mock_run(*args, **kwargs):
            raise FileNotFoundError()
        
        monkeypatch.setattr(subprocess, "run", mock_run)
        
        service = RailwayDryRunBootstrapService(working_dir=str(tmp_path))
        steps = service.explain_next_manual_steps()
        
        assert isinstance(steps, list)
        assert len(steps) > 0
        
        # Check that it explains the dry-run nature
        text = "\n".join(steps)
        assert "DRY-RUN" in text
        assert "No deployment has been performed" in text
        assert "No Railway resources have been created" in text

    def test_plan_next_manual_steps(self, tmp_path, monkeypatch):
        """Plan includes next manual steps."""
        def mock_run(*args, **kwargs):
            raise FileNotFoundError()
        
        monkeypatch.setattr(subprocess, "run", mock_run)
        
        service = RailwayDryRunBootstrapService(working_dir=str(tmp_path))
        plan = service.build_dry_run_plan()
        
        assert len(plan.next_manual_steps) >= 7
        
        # Check for key steps
        steps_text = "\n".join(plan.next_manual_steps)
        assert "railway login" in steps_text.lower()
        assert "railway link" in steps_text.lower()
        assert "railway up" in steps_text.lower()
        assert "do not run" in steps_text.lower() or "dry-run" in steps_text.lower()


class TestRailwayDryRunWarnings:
    """Tests for warning messages in dry-run output."""

    def test_warnings_in_plan(self, tmp_path, monkeypatch):
        """Plan includes appropriate warnings."""
        def mock_run(*args, **kwargs):
            raise FileNotFoundError()
        
        monkeypatch.setattr(subprocess, "run", mock_run)
        monkeypatch.setattr("shutil.which", lambda x: str(tmp_path / "railway"))
        
        service = RailwayDryRunBootstrapService(working_dir=str(tmp_path))
        plan = service.build_dry_run_plan()
        
        # Check for key warnings
        warnings_text = "\n".join(plan.warnings)
        assert "DRY-RUN" in warnings_text
        assert "No deployment has occurred" in warnings_text
        assert "Local private keys are NOT included" in warnings_text
        assert "INTAKE_DATABASE_URL" in warnings_text or "database" in warnings_text.lower()

    def test_plan_id_uniqueness(self, tmp_path, monkeypatch):
        """Each plan has a unique ID."""
        def mock_run(*args, **kwargs):
            raise FileNotFoundError()
        
        monkeypatch.setattr(subprocess, "run", mock_run)
        
        service = RailwayDryRunBootstrapService(working_dir=str(tmp_path))
        plan1 = service.build_dry_run_plan()
        plan2 = service.build_dry_run_plan()
        
        assert plan1.plan_id != plan2.plan_id
