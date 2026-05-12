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
        default="sqlite:///./.build/intake/local.db"
    )

    # Development encryption key (32-byte URL-safe base64)
    intake_dev_encryption_key: SecretStr | None = Field(
        default=None
    )

    # Session secret
    intake_session_secret: SecretStr | None = Field(
        default=None
    )

    # Challenge expiry in seconds
    intake_challenge_expiry: int = Field(default=300)

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.intake_env == "production"

    @property
    def is_local(self) -> bool:
        """Check if running in local development environment."""
        return self.intake_env == "local"

    def ensure_build_dir(self) -> Path:
        """Ensure the build directory exists."""
        build_path = Path(".build/intake")
        build_path.mkdir(parents=True, exist_ok=True)
        return build_path

    def get_database_url_for_sqlmodel(self) -> str:
        """Get database URL compatible with SQLModel/SQLAlchemy."""
        url = self.intake_database_url
        # Replace sqlite:/// with sqlite://// for absolute paths
        if url.startswith("sqlite:///"):
            url = "sqlite:///" + os.path.abspath(url[11:])
        return url


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def reset_settings() -> None:
    """Reset the cached settings (useful for testing)."""
    get_settings.cache_clear()
