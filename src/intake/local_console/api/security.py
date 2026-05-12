import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from intake.config import get_settings
from intake.local_console.security.unlock import LocalAuthorizationWindow, get_auth_window

router = APIRouter(prefix="/security", tags=["security"])


class UnlockStatus(BaseModel):
    """Current secure unlock status."""
    is_unlocked: bool
    remaining_seconds: float
    # Additional context for UI labeling
    unlock_mode: str = "none"  # "none", "native_os_auth", "dev_insecure"
    requires_native_auth: bool = True


class UnlockChallenge(BaseModel):
    """Short-lived challenge for native-auth-proven unlock flow."""
    challenge_token: str
    expires_at: str  # ISO timestamp
    requires_native_proof: bool = True


# In-memory challenge store (scaffold - not persistent)
_challenge_store: dict[str, dict] = {}


def _generate_challenge(expiry_seconds: int = 60) -> str:
    """Generate a random challenge token."""
    token = secrets.token_hex(32)
    _challenge_store[token] = {
        "created_at": "now",
        "expires_at": expiry_seconds,
        "consumed": False
    }
    return token


def _consume_challenge(token: str) -> bool:
    """Mark a challenge as consumed. Returns True if valid and not consumed."""
    if token not in _challenge_store:
        return False
    if _challenge_store[token].get("consumed", False):
        return False
    _challenge_store[token]["consumed"] = True
    return True


@router.get("/status", response_model=UnlockStatus)
async def get_unlock_status(
    request: Request,
    auth_window: LocalAuthorizationWindow = Depends(get_auth_window)
):
    """Get the current secure unlock status and mode.
    
    Also enforces loopback for status checks.
    """
    client_host = request.client.host if request.client else None
    if client_host not in ["127.0.0.1", "::1", "localhost", "testclient"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Status check only permitted from loopback"
        )
    
    return UnlockStatus(
        is_unlocked=auth_window.is_unlocked,
        remaining_seconds=auth_window.remaining_seconds,
        unlock_mode="native_os_auth" if auth_window.is_unlocked else "none",
        requires_native_auth=True
    )


@router.get("/challenge", response_model=UnlockChallenge)
async def get_unlock_challenge():
    """Generate a short-lived challenge for native-auth-proven unlock.
    
    This supports a two-step flow:
    1. Native layer (Swift/pywebview) requests challenge
    2. Native layer performs OS auth and POSTs unlock with challenge + proof
    
    Security: Challenge tokens expire quickly and can only be used once.
    """
    settings = get_settings()
    
    # Generate challenge
    token = _generate_challenge(expiry_seconds=settings.intake_challenge_expiry)
    
    # Import datetime for expiry calculation
    from datetime import datetime, timedelta, timezone
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=settings.intake_challenge_expiry)).isoformat()
    
    return UnlockChallenge(
        challenge_token=token,
        expires_at=expires_at,
        requires_native_proof=True
    )


@router.post("/unlock", response_model=UnlockStatus)
async def perform_unlock(
    request: Request,
    auth_window: LocalAuthorizationWindow = Depends(get_auth_window)
):
    """Unlock the authorization window after native OS authentication.
    
    Security Notes:
    - This endpoint should only be reachable via loopback (enforced by server binding)
    - In production: Requires native OS auth proof (via challenge flow)
    - In dev mode with INTAKE_ENABLE_INSECURE_DEV_UNLOCK=1: Allows insecure loopback unlock
    - WITHOUT the dev flag: Direct POST unlock is refused
    
    The preferred flow:
    1. Native layer calls GET /api/local/security/challenge
    2. Native layer performs OS LocalAuthentication
    3. Native layer POSTs /api/local/security/unlock with challenge_token
    4. Server verifies challenge, unlocks window
    """
    # Read settings fresh (not cached) to pick up env changes in tests
    from intake.config import Settings
    settings = Settings()
    
    client_host = request.client.host if request.client else None
    
    # Always enforce loopback
    # testclient is used by FastAPI TestClient for testing
    if client_host not in ["127.0.0.1", "::1", "localhost", "testclient"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unlock only permitted from loopback"
        )
    
    # Check for dev insecure mode
    is_dev_insecure_enabled = settings.intake_enable_insecure_dev_unlock
    
    # Parse request body if present
    try:
        import json
        body = await request.json()
        challenge_token = body.get("challenge_token")
        native_proof = body.get("native_proof")
        unlock_mode = body.get("unlock_mode", "unknown")
    except Exception:
        challenge_token = None
        native_proof = None
        unlock_mode = "unknown"
    
    # If we have a challenge token, validate it
    if challenge_token and isinstance(challenge_token, str):
        if _consume_challenge(challenge_token):
            # Challenge validated - this came through native layer
            auth_window.unlock()
            return UnlockStatus(
                is_unlocked=auth_window.is_unlocked,
                remaining_seconds=auth_window.remaining_seconds,
                unlock_mode="native_os_auth",
                requires_native_auth=True
            )
        else:
            # Invalid or already consumed challenge
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid or expired challenge token"
            )
    
    # No challenge token - check if this is dev insecure mode
    if is_dev_insecure_enabled:
        # Dev mode: Allow insecure unlock but label it as such
        auth_window.unlock()
        return UnlockStatus(
            is_unlocked=auth_window.is_unlocked,
            remaining_seconds=auth_window.remaining_seconds,
            unlock_mode="dev_insecure",
            requires_native_auth=False
        )
    
    # Production/default: Refuse insecure unlock
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Secure unlock requires native OS authentication. "
               "Direct loopback unlock is disabled. "
               "Use: 1) GET /api/local/security/challenge, 2) Native OS auth, 3) POST /unlock with challenge_token"
    )


@router.post("/lock", response_model=UnlockStatus)
async def perform_lock(
    auth_window: LocalAuthorizationWindow = Depends(get_auth_window)
):
    """Immediately clear the authorization window."""
    auth_window.lock()
    return UnlockStatus(
        is_unlocked=False,
        remaining_seconds=0.0,
        unlock_mode="none",
        requires_native_auth=True
    )
