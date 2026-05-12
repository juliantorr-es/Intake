"""Intake deployment package.

This package provides:
- Deployment adapter architecture for multiple cloud providers
- Railway dry-run bootstrap capability
- Upload provider models and routing
- Provider configuration redaction utilities
"""

from intake.deploy.models import (
    DeploymentProvider,
    DeploymentPlan,
    DeploymentArtifact,
    DeploymentEnvironmentSpec,
    DeploymentReceipt,
    DeploymentTarget,
)

from intake.deploy.registry import (
    get_adapter,
    list_supported_providers,
)

# Provider redaction utilities
from intake.deploy.provider_redaction import (
    redact_secret_value,
    redact_dict_keys,
    redact_file_paths,
    sanitize_provider_config,
    get_redacted_fields,
    REDACTED_PLACEHOLDER,
    FILE_PATH_PLACEHOLDER,
)

__all__ = [
    # Deployment models
    "DeploymentProvider",
    "DeploymentPlan",
    "DeploymentArtifact", 
    "DeploymentEnvironmentSpec",
    "DeploymentReceipt",
    "DeploymentTarget",
    # Registry
    "get_adapter",
    "list_supported_providers",
    # Redaction utilities
    "redact_secret_value",
    "redact_dict_keys",
    "redact_file_paths",
    "sanitize_provider_config",
    "get_redacted_fields",
    "REDACTED_PLACEHOLDER",
    "FILE_PATH_PLACEHOLDER",
]
