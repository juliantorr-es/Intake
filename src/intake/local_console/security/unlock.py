"""In-memory authorization window for Local Secure Unlock."""

import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from pydantic import BaseModel

from intake.config import get_settings


class UnlockStatus(BaseModel):
    """Current state of the local authorization window."""
    is_unlocked: bool
    expires_at: Optional[datetime] = None
    seconds_remaining: float = 0.0


class LocalAuthorizationWindow:
    """Manages a short-lived local authorization window.
    
    This is process-local state that tracks if the operator has recently
    performed a Local Secure Unlock (biometric/presence check).
    """

    def __init__(self, ttl_seconds: int = 120):
        self._ttl_seconds = ttl_seconds
        self._expires_at: Optional[datetime] = None

    def unlock(self) -> None:
        """Create or refresh the authorization window."""
        settings = get_settings()
        ttl = settings.intake_local_unlock_ttl_seconds
        self._expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
        print(f"LocalAuthorizationWindow: Unlocked until {self._expires_at}")

    def lock(self) -> None:
        """Immediately clear the authorization window."""
        self._expires_at = None
        print("LocalAuthorizationWindow: Locked.")

    @property
    def is_unlocked(self) -> bool:
        """Check if the authorization window is currently active."""
        if self._expires_at is None:
            return False
        
        now = datetime.now(timezone.utc)
        if now > self._expires_at:
            self._expires_at = None  # Clean up expired window
            return False
        
        return True

    def get_status(self) -> UnlockStatus:
        """Get the current status of the window."""
        is_unlocked = self.is_unlocked
        expires_at = self._expires_at if is_unlocked else None
        
        remaining = 0.0
        if expires_at:
            remaining = max(0.0, (expires_at - datetime.now(timezone.utc)).total_seconds())
            
        return UnlockStatus(
            is_unlocked=is_unlocked,
            expires_at=expires_at,
            seconds_remaining=remaining
        )


# Singleton instance for the local process
_window = None

def get_auth_window() -> LocalAuthorizationWindow:
    """Get the process-wide authorization window."""
    global _window
    if _window is None:
        settings = get_settings()
        _window = LocalAuthorizationWindow(ttl_seconds=settings.intake_local_unlock_ttl_seconds)
    return _window


def reset_auth_window() -> None:
    """Reset the global authorization window (useful for testing)."""
    global _window
    _window = None
