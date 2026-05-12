"""Configuration management for Intake."""

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Environment
    intake_env: str = Field(default="local")

    # Base URL
    intake_base_url: str = Field(default="http://127.0.0.1:8000")

    # WebAuthn / Passkey relying party
    intake_rp_id: str = Field(default="localhost")
    intake_rp_name: str = Field(default="Intake Local")
    intake_origin: str = Field(default="http://localhost:8000")

    # Database
    intake_database_url: str = Field(
        default="sqlite:///:memory:"
    )

    # Development encryption key (32-byte URL-safe base64)
    intake_dev_encryption_key: SecretStr | None = Field(
        default=None
    )

    # Session secret
    intake_session_secret: SecretStr | None = Field(
        default=None
    )

    # Temporary local-dev sync token for operator sync auth
    # This is NOT the final operator-device auth model.
    intake_local_sync_token: SecretStr | None = Field(
        default=None
    )
    intake_local_signing_key: SecretStr | None = Field(
        default=None
    )
    intake_enable_dev_sync_auth: bool = Field(default=True)

    # Session cookie configuration
    intake_session_cookie_name: str = Field(default="intake_session")
    intake_session_cookie_secure: bool | None = Field(default=None)
    intake_session_cookie_httponly: bool = Field(default=True)
    intake_session_cookie_samesite: str = Field(default="lax")
    intake_session_ttl_seconds: int = Field(default=24 * 60 * 60)  # 24 hours

    # Challenge expiry in seconds
    intake_challenge_expiry: int = Field(default=300)

    # Email verification
    intake_require_verified_email_for_uploads: bool = Field(default=True)
    intake_require_verified_email_for_quote_submit: bool = Field(default=True)
    intake_email_code_ttl_seconds: int = Field(default=900)
    intake_email_code_max_attempts: int = Field(default=5)
    # Local Secure Unlock
    intake_require_local_unlock_for_decrypt: bool = Field(default=True)
    intake_local_unlock_ttl_seconds: int = Field(default=120)

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.intake_env == "production"

    @property
    def is_local(self) -> bool:
        """Check if running in local development environment."""
        return self.intake_env == "local"

    @property
    def session_cookie_secure(self) -> bool:
        """Get effective session cookie Secure flag.
        
        Returns True in production, False in local unless explicitly set.
        """
        if self.intake_session_cookie_secure is not None:
            return self.intake_session_cookie_secure
        return self.is_production

    @property
    def workspace_root(self) -> Path:
        """Get the workspace root directory."""
        return Path(__file__).parent.parent.parent.parent

    def ensure_build_dir(self) -> Path:
        """Ensure the build/data directory exists."""
        build_path = self.workspace_root / ".build" / "intake"
        build_path.mkdir(parents=True, exist_ok=True)
        return build_path

    def get_database_url_for_sqlmodel(self) -> str:
        """Get database URL compatible with SQLModel/SQLAlchemy."""
        url = self.intake_database_url
        if url.startswith("sqlite:///"):
            # Ensure the data directory exists
            self.ensure_build_dir()
            # For sqlite:///, the path after the prefix should be absolute
            # If it starts with /, keep it as-is with 4 slashes
            # If it's relative, make it absolute with 4 slashes
            path = url[10:]  # Remove "sqlite://"
            if path.startswith("/"):
                # Already absolute path, use 4 slashes
                url = "sqlite://" + path
            else:
                # Relative path, make absolute
                url = "sqlite:///" + os.path.abspath(path)
        return url


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def reset_settings() -> None:
    """Reset the cached settings (useful for testing)."""
    get_settings.cache_clear()
