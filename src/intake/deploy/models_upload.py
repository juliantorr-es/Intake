"""Upload provider models for open upload/provider architecture."""

from datetime import datetime
from enum import StrEnum, auto
from typing import Any, Optional
from pydantic import BaseModel, Field, ConfigDict


class UploadProviderKind(StrEnum):
    """All planned upload provider kinds for Intake's local-first architecture."""
    # Local receiver: client uploads directly to local Intake instance
    LOCAL_LOOPBACK_DEV = "local_loopback_dev"
    
    # Tunnel providers: expose local receiver publicly
    TAILSCALE_FUNNEL_FUTURE = "tailscale_funnel_future"
    CLOUDFLARE_TUNNEL_FUTURE = "cloudflare_tunnel_future"
    
    # Fallback storage providers: cloud storage for when local is offline
    GOOGLE_DRIVE_FALLBACK_FUTURE = "google_drive_fallback_future"
    HOSTED_BUFFER_FUTURE = "hosted_buffer_future"
    S3_COMPATIBLE_FUTURE = "s3_compatible_future"
    CLOUDFLARE_R2_FUTURE = "cloudflare_r2_future"
    CLOUDKIT_ICLOUD_EXPERIMENTAL = "cloudkit_icloud_experimental"
    
    # Resumable upload protocol
    TUS_RESUMABLE_FUTURE = "tus_resumable_future"


class UploadProviderCapability(StrEnum):
    """Capabilities that upload providers may support."""
    DIRECT_UPLOAD = "DIRECT_UPLOAD"
    RESUMABLE_UPLOAD = "RESUMABLE_UPLOAD"
    CHUNKED_UPLOAD = "CHUNKED_UPLOAD"
    STREAMING_UPLOAD = "STREAMING_UPLOAD"
    LARGE_FILE = "LARGE_FILE"
    CUSTOM_DOMAIN = "CUSTOM_DOMAIN"
    END_TO_END_ENCRYPTION = "END_TO_END_ENCRYPTION"
    DEVICE_SYNC = "DEVICE_SYNC"
    WEBHOOK_NOTIFICATION = "WEBHOOK_NOTIFICATION"


class UploadProviderStatus(StrEnum):
    """Current status of an upload provider."""
    NOT_CONFIGURED = "not_configured"
    CONFIGURED = "configured"
    CONNECTED = "connected"
    OFFLINE = "offline"
    ERROR = "error"


class ProviderConfigRedacted(BaseModel):
    """Provider configuration with all secrets redacted.
    
    This model ensures that no credentials or tokens are exposed
    in logs, API responses, or UI displays.
    """
    model_config = ConfigDict(json_schema_extra={
        "examples": [{
            "kind": "local_loopback_dev",
            "display_name": "Local Loopback",
            "capabilities": ["DIRECT_UPLOAD", "STREAMING_UPLOAD"],
            "status": "CONFIGURED",
            "redacted_fields": ["INTAKE_LOCAL_SYNC_TOKEN"]
        }]
    })
    
    kind: UploadProviderKind
    display_name: str
    capabilities: list[UploadProviderCapability] = []
    status: UploadProviderStatus = UploadProviderStatus.NOT_CONFIGURED
    endpoint_url: Optional[str] = None
    # Fields that were redacted (for audit purposes, not for display)
    redacted_fields: list[str] = []
    # Non-sensitive metadata
    metadata: dict[str, Any] = Field(default_factory=dict)


class UploadProviderPlan(BaseModel):
    """Plan for configuring an upload provider."""
    kind: UploadProviderKind
    display_name: str
    description: str
    capabilities: list[UploadProviderCapability] = []
    requires_credentials: bool = False
    requires_installation: bool = False
    requires_network_access: bool = False
    priority: int = 0  # Lower = higher priority
    is_future: bool = True
    implementation_status: str = "planned"


class ReceiverHandshakeResult(BaseModel):
    """Result of a handshake attempt with a local upload receiver."""
    receiver_kind: UploadProviderKind
    success: bool
    endpoint_url: Optional[str] = None
    handshake_latency_ms: Optional[float] = None
    error: Optional[str] = None
    receiver_version: Optional[str] = None
    requires_auth: bool = False
    auth_providers: list[str] = []
    handshake_timestamp: datetime = Field(default_factory=datetime.now)


class UploadRouteDecision(BaseModel):
    """Decides where to route an upload based on provider availability.
    
    Priority order:
    1. Local receiver if online and handshake succeeds
    2. Fallback provider if configured
    3. Quote submission without files or retry-later state
    """
    chosen_provider: UploadProviderKind
    route_priority: int  # 1 = highest
    route_reason: str
    fallback_available: bool = False
    fallback_provider: Optional[UploadProviderKind] = None
    upload_endpoint: str
    # Session/token for this upload (not credentials - temporary auth)
    upload_session: Optional[dict[str, str]] = None
    expires_at: Optional[datetime] = None


class UploadFallbackPolicy(BaseModel):
    """Policy governing fallback behavior when primary upload route fails.
    
    This policy serializes without provider credentials - only
    references to provider kinds and non-sensitive configuration.
    """
    primary_provider: UploadProviderKind
    fallback_providers: list[UploadProviderKind] = []
    max_retries: int = 3
    retry_delay_seconds: float = 2.0
    fallback_expiry_minutes: int = 60
    require_resumable_uploads: bool = False
    min_chunk_size_bytes: int = 5 * 1024 * 1024  # 5MB
    # Non-sensitive threshold configuration
    large_file_threshold_bytes: int = 100 * 1024 * 1024  # 100MB


class ProviderHealthCheck(BaseModel):
    """Health check result for a provider."""
    kind: UploadProviderKind
    healthy: bool
    latency_ms: Optional[float] = None
    last_checked: datetime = Field(default_factory=datetime.now)
    error: Optional[str] = None
