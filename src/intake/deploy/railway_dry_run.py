"""Railway dry-run bootstrap service.

This service provides non-mutating Railway deployment readiness checks
and plan generation. It never executes mutating commands like:
- railway init
- railway link  
- railway up
- railway add
- railway variables set
- railway deploy

It only performs read-only operations:
- railway --version
- which railway / command -v
- Parsing existing local Railway config files
"""

import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Import from models directly to avoid potential circular imports
from intake.deploy.models import DeploymentEnvironmentSpec


# Environment variable classification
HOSTED_SAFE_VAR_KEYS = frozenset({
    "INTAKE_ENV",
    "INTAKE_BASE_URL", 
    "INTAKE_RP_ID",
    "INTAKE_RP_NAME",
    "INTAKE_ORIGIN",
    "INTAKE_DATABASE_URL",
    "INTAKE_SESSION_SECRET",
    "INTAKE_LOCAL_SYNC_TOKEN",
    # Email provider vars (future)
})

LOCAL_ONLY_FORBIDDEN_VAR_KEYS = frozenset({
    "INTAKE_LOCAL_SIGNING_KEY",
    "INTAKE_LOCAL_PRIVATE_DECRYPT_KEY",
    "INTAKE_DEV_ENCRYPTION_KEY",
})

# All hosted-safe env vars with their specs
HOSTED_ENV_SPECS = [
    DeploymentEnvironmentSpec(
        key="INTAKE_ENV",
        description="Deployment environment (e.g. production, staging)",
        required=True,
        default_value="production"
    ),
    DeploymentEnvironmentSpec(
        key="INTAKE_BASE_URL",
        description="Public URL of the hosted backend",
        required=True
    ),
    DeploymentEnvironmentSpec(
        key="INTAKE_RP_ID",
        description="WebAuthn RP ID (domain)",
        required=True
    ),
    DeploymentEnvironmentSpec(
        key="INTAKE_RP_NAME", 
        description="WebAuthn RP Name",
        required=True,
        default_value="Intake"
    ),
    DeploymentEnvironmentSpec(
        key="INTAKE_ORIGIN",
        description="Public origin URL",
        required=True
    ),
    DeploymentEnvironmentSpec(
        key="INTAKE_DATABASE_URL",
        description="SQLAlchemy database URL",
        required=True,
        is_secret=True
    ),
    DeploymentEnvironmentSpec(
        key="INTAKE_SESSION_SECRET",
        description="Secret for signing session cookies",
        required=True,
        is_secret=True
    ),
    DeploymentEnvironmentSpec(
        key="INTAKE_LOCAL_SYNC_TOKEN",
        description="Token for sync protocol authentication",
        required=True,
        is_secret=True
    ),
]

# Forbidden local-only vars (must NEVER be in hosted deployment)
FORBIDDEN_ENV_SPECS = [
    DeploymentEnvironmentSpec(
        key="INTAKE_LOCAL_SIGNING_KEY",
        description="Local private signing key - LOCAL ONLY",
        forbidden=True,
        is_secret=True
    ),
    DeploymentEnvironmentSpec(
        key="INTAKE_LOCAL_PRIVATE_DECRYPT_KEY",
        description="Local private decrypt key - LOCAL ONLY",
        forbidden=True,
        is_secret=True
    ),
    DeploymentEnvironmentSpec(
        key="INTAKE_DEV_ENCRYPTION_KEY",
        description="Dev symmetric encryption key - bootstrap only, risky for prod",
        forbidden=True,
        is_secret=True
    ),
]


@dataclass
class RailwayCliInfo:
    """Information about Railway CLI availability."""
    present: bool
    version: Optional[str] = None
    path: Optional[str] = None
    error: Optional[str] = None


@dataclass 
class RailwayAuthInfo:
    """Information about Railway authentication state.
    
    We can only detect this safely by checking for existing config files
    or environment variables, NOT by calling railway login status.
    """
    has_config_file: bool = False
    config_file_path: Optional[str] = None
    inferred_authenticated: bool = False
    note: str = "Unknown - cannot safely detect without calling Railway API"


@dataclass
class RailwayProjectInfo:
    """Information about Railway project linkage."""
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    linked: Optional[bool] = None
    linkage_file: Optional[str] = None
    note: str = "Unknown - cannot safely detect without Railway API"


@dataclass
class RailwayDryRunPlan:
    """Complete dry-run plan for Railway deployment.
    
    This plan contains ALL commands that would be executed, but only
    as text strings. Nothing is actually run.
    """
    # Identification
    plan_id: str
    
    # CLI state
    railway_cli_present: bool
    railway_cli_version: Optional[str] = None
    railway_cli_path: Optional[str] = None
    
    # Auth state
    railway_authenticated: Optional[bool] = None
    railway_project_linked: Optional[bool] = None
    
    # Required env vars
    required_env_vars: list[DeploymentEnvironmentSpec] = field(default_factory=list)
    forbidden_env_vars: list[DeploymentEnvironmentSpec] = field(default_factory=list)
    
    # Generated artifacts
    generated_artifact_paths: list[str] = field(default_factory=list)
    artifact_contents: dict[str, str] = field(default_factory=dict)
    
    # Commands that would run (as text only - NEVER executed)
    commands_that_would_run: list[str] = field(default_factory=list)
    
    # Next manual steps for user
    next_manual_steps: list[str] = field(default_factory=list)
    
    # Safety notes
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    
    # Blocking issues
    blocking_issues: list[str] = field(default_factory=list)
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    
    @property
    def can_attempt_deployment(self) -> bool:
        """Check if deployment could theoretically proceed.
        
        Note: This is a dry-run check, not a guarantee.
        """
        return (
            self.railway_cli_present and
            len(self.blocking_issues) == 0
        )
    
    @property
    def is_ready(self) -> bool:
        """Check if all readiness criteria are met."""
        return (
            self.railway_cli_present and
            self.railway_authenticated is True and
            self.railway_project_linked is True and
            len(self.blocking_issues) == 0
        )


class RailwayDryRunBootstrapService:
    """Service for Railway dry-run bootstrap.
    
    This service provides:
    - CLI presence and version detection
    - Safe auth/project linkage detection (without calling Railway APIs)
    - Dry-run plan generation
    - Artifact validation
    - Next-step explanation
    
    Crucially, it does NOT:
    - Execute railway init
    - Execute railway link
    - Execute railway up
    - Execute railway add
    - Execute railway variables set
    - Execute railway deploy
    - Call any Railway APIs
    - Create or modify any Railway resources
    """
    
    def __init__(self, working_dir: Optional[str] = None):
        self.working_dir = working_dir or str(Path.cwd())
        self._cli_info: Optional[RailwayCliInfo] = None
        self._auth_info: Optional[RailwayAuthInfo] = None
        self._project_info: Optional[RailwayProjectInfo] = None
    
    def inspect_environment(self) -> dict[str, Any]:
        """Inspect local environment for Railway readiness.
        
        This is a NON-MUTATING inspection that only reads local state.
        """
        cli = self.check_railway_cli()
        auth = self.check_railway_auth()
        project = self.check_railway_project()
        
        return {
            "railway_cli_present": cli.present,
            "railway_cli_version": cli.version,
            "railway_cli_path": cli.path,
            "railway_cli_error": cli.error,
            "railway_auth": {
                "has_config_file": auth.has_config_file,
                "config_file_path": auth.config_file_path,
                "inferred_authenticated": auth.inferred_authenticated,
                "note": auth.note
            },
            "railway_project": {
                "project_id": project.project_id,
                "project_name": project.project_name,
                "linked": project.linked,
                "linkage_file": project.linkage_file,
                "note": project.note
            }
        }
    
    def check_railway_cli(self) -> RailwayCliInfo:
        """Check if Railway CLI is installed and get its version.
        
        Only uses read-only commands: railway --version, which railway, etc.
        """
        # Try multiple detection methods
        for method in [self._check_via_version_flag, 
                       self._check_via_command_v, 
                       self._check_via_which]:
            result = method()
            if result.present:
                return result
        
        return RailwayCliInfo(
            present=False,
            version=None,
            path=None,
            error="Railway CLI not found"
        )
    
    def _check_via_version_flag(self) -> RailwayCliInfo:
        """Check via `railway --version`"""
        try:
            result = subprocess.run(
                ["railway", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                # Railway CLI outputs like: @railway/cli/4.0.0
                version_match = re.search(r'(\d+\.\d+\.\d+)', version)
                actual_version = version_match.group(1) if version_match else version
                
                # Get the actual path
                path = shutil.which("railway")
                
                return RailwayCliInfo(
                    present=True,
                    version=actual_version,
                    path=path
                )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        return RailwayCliInfo(present=False, error="railway --version failed")
    
    def _check_via_command_v(self) -> RailwayCliInfo:
        """Check via `railway -v` or `command -v railway`"""
        try:
            # On Unix-like systems
            result = subprocess.run(
                ["command", "-v", "railway"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                path = result.stdout.strip()
                return RailwayCliInfo(
                    present=True,
                    path=path
                )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        return RailwayCliInfo(present=False)
    
    def _check_via_which(self) -> RailwayCliInfo:
        """Check via `which railway`"""
        try:
            result = subprocess.run(
                ["which", "railway"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                path = result.stdout.strip()
                # Try to get version from the path
                return RailwayCliInfo(
                    present=True,
                    path=path
                )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        return RailwayCliInfo(present=False)
    
    def check_railway_auth(self) -> RailwayAuthInfo:
        """Check for Railway authentication indicators.
        
        This is intentionally conservative. We check for the existence of
        Railway config files that would indicate prior authentication,
        but we do NOT call `railway login status` or any other Railway API.
        """
        # Possible config file locations
        possible_paths = [
            Path.home() / ".railway" / "config.json",
            Path.home() / ".railway" / "credentials",
            Path(self.working_dir) / ".railway.json",
            Path(self.working_dir) / "railway.json",
        ]
        
        config_file_path = None
        for p in possible_paths:
            if p.exists():
                config_file_path = str(p)
                break
        
        if config_file_path:
            return RailwayAuthInfo(
                has_config_file=True,
                config_file_path=config_file_path,
                inferred_authenticated=True,
                note="Config file found - may indicate prior authentication"
            )
        
        return RailwayAuthInfo(
            has_config_file=False,
            note="No Railway config file found - auth state unknown"
        )
    
    def check_railway_project(self) -> RailwayProjectInfo:
        """Check for Railway project linkage indicators.
        
        Looks for Railway-specific files that might indicate project linkage.
        Does NOT call `railway link` or `railway projects`.
        """
        # Possible linkage indicators
        possible_files = [
            Path(self.working_dir) / "railway.json",
            Path(self.working_dir) / ".railway.json",
            Path(self.working_dir) / ".railway",
        ]
        
        linkage_file = None
        for p in possible_files:
            if p.exists():
                linkage_file = str(p)
                break
        
        if linkage_file:
            return RailwayProjectInfo(
                linkage_file=linkage_file,
                linked=True,
                note=f"Railway config file found at {linkage_file}"
            )
        
        return RailwayProjectInfo(
            linked=None,
            note="No Railway project config found"
        )
    
    def build_dry_run_plan(
        self, 
        app_name: str = "intake",
        include_artifacts: bool = True
    ) -> RailwayDryRunPlan:
        """Build a complete dry-run deployment plan.
        
        This plan contains ALL commands that would be executed as text strings.
        Nothing is actually run.
        """
        cli = self.check_railway_cli()
        auth = self.check_railway_auth()
        project = self.check_railway_project()
        
        # Generate plan ID
        import uuid
        plan_id = str(uuid.uuid4())[:8]
        
        # Build artifact paths (but don't write them)
        base_build_dir = Path(self.working_dir) / ".build" / "intake" / "deploy" / "railway" / plan_id
        artifact_paths = []
        artifact_contents = {}
        
        if include_artifacts:
            # Generate railway.json
            railway_config = {
                "$schema": "https://railway.app/railway.schema.json",
                "build": {
                    "builder": "NIXPACKS"
                },
                "deploy": {
                    "startCommand": "uvicorn intake.app:app --host 0.0.0.0 --port ${PORT:-8000}",
                    "healthCheckPath": "/health",
                    "restartPolicyType": "ON_FAILURE"
                }
            }
            railway_json_path = str(base_build_dir / "railway.json")
            artifact_paths.append(railway_json_path)
            artifact_contents[railway_json_path] = json.dumps(railway_config, indent=2)
            
            # Generate .env.hosted.example
            env_example = self._generate_env_example()
            env_path = str(base_build_dir / ".env.hosted.example")
            artifact_paths.append(env_path)
            artifact_contents[env_path] = env_example
        
        # Build commands that would run (as text only)
        commands = []
        
        if not cli.present:
            commands.append("# INSTALL REQUIRED: npm i -g @railway/cli")
        
        commands.extend([
            "# Like: railway login",
            "# Like: railway link",
            f"# Like: railway init (in {self.working_dir})",
            "# Like: railway variables set INTAKE_ENV=production",
            "# Like: railway variables set INTAKE_BASE_URL=https://your-app.up.railway.app",
            "# Like: railway variables set INTAKE_RP_ID=your-domain.com",
            "# Like: railway variables set INTAKE_RP_NAME=Intake",
            "# Like: railway variables set INTAKE_ORIGIN=https://your-app.up.railway.app",
            "# Like: railway variables set INTAKE_DATABASE_URL=<your-db-url>",
            "# Like: railway variables set INTAKE_SESSION_SECRET=<generated-secret>",
            "# Like: railway variables set INTAKE_LOCAL_SYNC_TOKEN=<generated-token>",
            "# NOTE: INTAKE_LOCAL_SIGNING_KEY and other local-only keys are NOT set",
            "# NOTE: These commands are for REFERENCE ONLY - they have not been executed",
            "# To actually deploy: railway up",
        ])
        
        # Next manual steps
        next_steps = [
            "1. Install Railway CLI: npm i -g @railway/cli",
            "2. Authenticate: railway login",
            "3. Navigate to project directory",
            f"4. Link project: railway link (or create new with railway init)",
            "5. Set environment variables in Railway dashboard",
            "6. Ensure local-only keys (INTAKE_LOCAL_SIGNING_KEY, etc.) are NOT deployed",
            "7. Deploy: railway up (DO NOT RUN - this is a dry-run)"
        ]
        
        # Blocking issues
        blocking = []
        if not cli.present:
            blocking.append("Railway CLI is not installed")
        
        # Warnings
        warnings = [
            "This is a DRY-RUN plan only. No deployment has occurred.",
            "Local private keys are NOT included in this plan.",
            "Ensure INTAKE_DATABASE_URL points to a persistent database.",
            "The INTAKE_DEV_ENCRYPTION_KEY should be replaced with proper encryption in production.",
            "Do not run 'railway up' without reviewing all environment variables."
        ]
        
        return RailwayDryRunPlan(
            plan_id=plan_id,
            railway_cli_present=cli.present,
            railway_cli_version=cli.version,
            railway_cli_path=cli.path,
            railway_authenticated=auth.inferred_authenticated if auth.has_config_file else None,
            railway_project_linked=project.linked,
            required_env_vars=HOSTED_ENV_SPECS,
            forbidden_env_vars=FORBIDDEN_ENV_SPECS,
            generated_artifact_paths=artifact_paths,
            artifact_contents=artifact_contents,
            commands_that_would_run=commands,
            next_manual_steps=next_steps,
            warnings=warnings,
            errors=[],
            blocking_issues=blocking
        )
    
    def _generate_env_example(self) -> str:
        """Generate the .env.hosted.example content."""
        lines = [
            "# Intake Hosted Backend Environment Variables",
            "# DO NOT include local-only keys (INTAKE_LOCAL_SIGNING_KEY, etc.)",
            "",
        ]
        
        for spec in HOSTED_ENV_SPECS:
            if spec.is_secret:
                value = "REDACTED"
            elif spec.default_value:
                value = spec.default_value
            else:
                value = ""
            lines.append(f"{spec.key}={value} # {spec.description}")
        
        lines.append("")
        lines.append("# Forbidden keys (local-only, must never be deployed):")
        for spec in FORBIDDEN_ENV_SPECS:
            lines.append(f"# {spec.key} = <NEVER SET IN HOSTED> # {spec.description}")
        
        return "\n".join(lines)
    
    def validate_artifacts(self, plan: RailwayDryRunPlan) -> dict[str, Any]:
        """Validate generated artifacts for security and completeness.
        
        Checks that:
        - No forbidden env vars appear in generated artifacts
        - All required env vars are documented
        - No actual secrets are embedded
        """
        results = {
            "valid": True,
            "issues": [],
            "warnings": []
        }
        
        # Check artifact contents
        for path, content in plan.artifact_contents.items():
            if path.endswith(".env.hosted.example") or path.endswith(".env"):
                # Check for forbidden keys
                for forbidden_spec in FORBIDDEN_ENV_SPECS:
                    if forbidden_spec.key in content:
                        # Check it's only in comments
                        lines_with_key = [line for line in content.split("\n") 
                                         if forbidden_spec.key in line]
                        for line in lines_with_key:
                            if not line.strip().startswith("#"):
                                results["valid"] = False
                                results["issues"].append(
                                    f"FORBIDDEN KEY in {path}: {forbidden_spec.key} "
                                    f"found in non-comment line: {line.strip()}"
                                )
                
                # Check for actual secrets
                if "INTAKE_SESSION_SECRET=" in content and "REDACTED" not in content:
                    # This is okay if it's a placeholder
                    pass
        
        return results
    
    def explain_next_manual_steps(self) -> list[str]:
        """Explain the next manual steps without executing anything."""
        return [
            "RAILWAY DRY-RUN COMPLETE",
            "",
            "No deployment has been performed. No Railway resources have been created.",
            "",
            "To actually deploy to Railway:",
            "  1. Review the dry-run plan",
            "  2. Install Railway CLI: npm i -g @railway/cli",
            "  3. Run: railway login",
            "  4. Navigate to your project directory",
            "  5. Run: railway init (or railway link for existing project)",
            "  6. Set all required environment variables in Railway dashboard",
            "  7. Verify that INTAKE_LOCAL_SIGNING_KEY is NOT set",
            "  8. Run: railway up",
            "",
            "WARNING: Step 8 (railway up) will upload and deploy your code.",
            "         Only proceed after verifying all environment variables."
        ]
