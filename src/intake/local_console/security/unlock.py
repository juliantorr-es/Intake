import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from intake.config import get_settings

logger = logging.getLogger(__name__)

class LocalAuthorizationWindow:
    """Manages the in-memory authorization window for Local Secure Unlock.
    
    This service tracks whether the local operator has recently performed 
    biometric/passcode verification through the native shell.
    
    Security Guarantee:
    - This state is in-memory only.
    - It expires after a configurable TTL (default 120s).
    - It can be manually cleared (locked).
    - It is NOT cryptographically bound to a secret yet (Scaffold phase).
    """
    
    _instance: Optional["LocalAuthorizationWindow"] = None
    
    def __init__(self):
        self._unlocked_until: Optional[datetime] = None
    
    @classmethod
    def get_instance(cls) -> "LocalAuthorizationWindow":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def unlock(self) -> datetime:
        """Refresh the authorization window."""
        settings = get_settings()
        ttl = settings.intake_local_unlock_ttl_seconds
        
        expiry = datetime.now(timezone.utc) + timedelta(seconds=ttl)
        self._unlocked_until = expiry
        
        logger.info(f"LocalAuthorizationWindow: Unlocked until {expiry}")
        return expiry
    
    def lock(self):
        """Immediately clear the authorization window."""
        self._unlocked_until = None
        logger.info("LocalAuthorizationWindow: Locked.")
    
    @property
    def is_unlocked(self) -> bool:
        """Check if the window is currently open and not expired."""
        if self._unlocked_until is None:
            return False
        
        if datetime.now(timezone.utc) > self._unlocked_until:
            self.lock()
            return False
            
        return True
    
    @property
    def remaining_seconds(self) -> float:
        """Get remaining time in the window."""
        if not self.is_unlocked:
            return 0.0
        
        delta = self._unlocked_until - datetime.now(timezone.utc)
        return max(0.0, delta.total_seconds())

def get_auth_window() -> LocalAuthorizationWindow:
    """Dependency provider for LocalAuthorizationWindow."""
    return LocalAuthorizationWindow.get_instance()

def reset_auth_window():
    """Helper for tests to clear state."""
    LocalAuthorizationWindow.get_instance().lock()
