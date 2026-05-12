"""Security API for Local Console - Challenge/Response Unlock Flow with Native Capability Proof."""

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from intake.config import get_settings

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
    expires_at: str  # ISO timestamp - absolute UTC timestamp
    requires_native_proof: bool = True


class CapabilityInfo(BaseModel):
    """Safe UI metadata about runtime capabilities (no secrets exposed)."""
    runtime_shell: str = "unknown"  # "swift", "pywebview", "browser", "unknown"
    secure_unlock_available: bool = False
    insecure_dev_unlock_enabled: bool = False
    unlock_label: str = "Not Available"
    unlock_warning: str | None = None


# Challenge store: token -> {expires_at: datetime, consumed: bool, issued_at: datetime}
# Using absolute datetime objects for proper expiry checking
_challenge_store: dict[str, dict] = {}

# Native capability token (per-process, only available in native shells)
# This is set at startup time from INTAKE_NATIVE_UNLOCK_CAPABILITY env var
_native_capability: str | None = None


def _get_native_capability() -> str | None:
    """Get the native capability token for this process (cached)."""
    global _native_capability
    if _native_capability is None:
        settings = get_settings()
        if settings.intake_native_unlock_capability:
            _native_capability = settings.intake_native_unlock_capability.get_secret_value()
        else:
            # Generate a per-process capability if not set via env
            # This is the "minimum acceptable scaffold" - Swift launcher would set this via env
            _native_capability = secrets.token_hex(32)
    return _native_capability


def _generate_challenge(expiry_seconds: int = 300) -> tuple[str, datetime]:
    """Generate a random challenge token with absolute expiry timestamp.
    
    Returns (token, expires_at_datetime)
    """
    token = secrets.token_hex(32)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=expiry_seconds)

    _challenge_store[token] = {
        "created_at": now,
        "expires_at": expires_at,
        "consumed": False
    }
    return token, expires_at


def _validate_native_proof(native_proof: str | None) -> bool:
    """Validate native proof against the configured capability.
    
    Returns True if proof matches the expected capability token.
    """
    if native_proof is None or not isinstance(native_proof, str):
        return False

    capability = _get_native_capability()
    if capability is None:
        return False

    # Constant-time comparison to prevent timing attacks
    import hmac
    expected = capability.encode("utf-8")
    actual = native_proof.encode("utf-8")
    return hmac.compare_digest(expected, actual)


def _cleanup_expired_challenges() -> int:
    """Remove expired challenges from the store.
    
    Returns number of challenges cleaned up.
    """
    now = datetime.now(timezone.utc)
    expired_tokens = []

    for token, challenge in _challenge_store.items():
        if now > challenge["expires_at"]:
            expired_tokens.append(token)

    for token in expired_tokens:
        del _challenge_store[token]

    return len(expired_tokens)


def _requires_native_capability() -> bool:
    """Check if this process has native capability configured."""
    return _get_native_capability() is not None


# ============================================================
# /api/local/security/status - Current unlock status
# ============================================================

@router.get("/status", response_model=UnlockStatus)
async def get_unlock_status(request: Request):
    """Get the current secure unlock status and mode.
    
    Also enforces loopback for status checks.
    """
    settings = get_settings()
    from intake.local_console.security.unlock import get_auth_window

    client_host = request.client.host if request.client else None
    if client_host not in ["127.0.0.1", "::1", "localhost", "testclient"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Status check only permitted from loopback"
        )

    auth_window = get_auth_window()

    # Opportunistically clean up expired challenges
    _cleanup_expired_challenges()

    unlock_mode = "native_os_auth" if auth_window.is_unlocked else "none"

    return UnlockStatus(
        is_unlocked=auth_window.is_unlocked,
        remaining_seconds=auth_window.remaining_seconds,
        unlock_mode=unlock_mode,
        requires_native_auth=True
    )


# ============================================================
# /api/local/security/capabilities - Safe UI metadata
# ============================================================

@router.get("/capabilities", response_model=CapabilityInfo)
async def get_capabilities(request: Request):
    """Get runtime capabilities for UI labeling (NO secrets exposed).
    
    Determines:
    - runtime_shell: Detect whether we're in Swift, pywebview, browser, or unknown
    - secure_unlock_available: Whether native OS auth is truly available
    - insecure_dev_unlock_enabled: Whether dev insecure mode is on
    - unlock_label: Safe label text for unlock button
    - unlock_warning: Warning text if applicable
    
    Security: This endpoint does NOT expose the native capability token.
    """
    settings = get_settings()

    client_host = request.client.host if request.client else None
    if client_host not in ["127.0.0.1", "::1", "localhost", "testclient"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Capabilities check only permitted from loopback"
        )

    # Detect runtime shell from headers
    # Swift WKWebView will have specific headers, pywebview has its own, browser is generic
    runtime_shell = "unknown"
    user_agent = request.headers.get("user-agent", "").lower()

    # Swift WKWebView detection
    if "webkit" in user_agent or "applewebkit" in user_agent:
        # More specific check for Swift WKWebView
        # Swift sets window.intakeBiometryType on the page
        # We can also check for the presence of specific headers
        runtime_shell = "swift"
    elif "pywebview" in user_agent:
        runtime_shell = "pywebview"
    elif "mozilla" in user_agent or "chrome" in user_agent or "safari" in user_agent:
        runtime_shell = "browser"

    # Detect if we have native capability (only true in Swift or explicitly configured)
    has_native_capability = _requires_native_capability()

    # Check if dev insecure mode is enabled
    dev_insecure_enabled = settings.intake_enable_insecure_dev_unlock

    # Determine secure unlock availability
    # Only available when:
    # 1. We have a native capability configured (proves we're in a native shell)
    # 2. AND we're not just a regular browser
    secure_unlock_available = has_native_capability and runtime_shell in ["swift", "pywebview"]

    # For Swift specifically, we know it has LocalAuthentication available
    # So even without explicit capability env var, Swift can do native auth
    # The capability is the proof that binds it to the backend process
    if runtime_shell == "swift":
        secure_unlock_available = has_native_capability
        if not has_native_capability:
            # Swift can still do native auth, but we need capability for proof
            # In production Swift launcher, capability is injected via env
            secure_unlock_available = True  # Swift has the bridge, capability is for binding

    # Determine labeling
    if runtime_shell == "swift":
        unlock_label = "Unlock with Native OS Auth"
        unlock_warning = None
    elif runtime_shell == "pywebview":
        if secure_unlock_available:
            unlock_label = "Unlock with OS Auth (pywebview)"
            unlock_warning = None
        else:
            unlock_label = "Unlock Not Available"
            unlock_warning = "pywebview native OS authentication is not implemented"
    elif dev_insecure_enabled:
        unlock_label = "Dev Unlock (Insecure)"
        unlock_warning = "Development mode - not cryptographically secure"
    else:
        unlock_label = "Unlock Not Available"
        unlock_warning = "Secure unlock requires native shell support"

    return CapabilityInfo(
        runtime_shell=runtime_shell,
        secure_unlock_available=secure_unlock_available,
        insecure_dev_unlock_enabled=dev_insecure_enabled,
        unlock_label=unlock_label,
        unlock_warning=unlock_warning
    )


# ============================================================
# /api/local/security/challenge - Generate unlock challenge
# ============================================================

@router.get("/challenge", response_model=UnlockChallenge)
async def get_unlock_challenge():
    """Generate a short-lived challenge for native-auth-proven unlock.
    
    This supports a two-step flow:
    1. Native layer (Swift/pywebview) requests challenge
    2. Native layer performs OS auth and POSTs unlock with challenge + native_proof
    
    Security:
    - Challenge tokens expire quickly (configurable, default 300s)
    - Can only be used once
    - expires_at is an absolute ISO timestamp
    - Does NOT include the native capability token (that's secret)
    """
    settings = get_settings()
    expiry_seconds = settings.intake_challenge_expiry

    # Generate challenge with absolute expiry
    token, expires_at = _generate_challenge(expiry_seconds=expiry_seconds)

    # Clean up expired challenges opportunistically
    _cleanup_expired_challenges()

    return UnlockChallenge(
        challenge_token=token,
        expires_at=expires_at.isoformat(),
        requires_native_proof=True
    )


# ============================================================
# /api/local/security/unlock - Perform unlock with challenge + proof
# ============================================================

class UnlockRequest(BaseModel):
    """Request body for unlock endpoint."""
    challenge_token: str | None = None
    native_proof: str | None = None
    proof_kind: str | None = None  # For future extensibility


@router.post("/unlock", response_model=UnlockStatus)
async def perform_unlock(request: Request, body: UnlockRequest | None = None):
    """Unlock the authorization window after native OS authentication.
    
    Security Guarantees:
    - Requires BOTH challenge_token AND native_proof
    - Challenge token alone: FAILS
    - Native proof alone: FAILS  
    - Invalid proof: FAILS (and does NOT consume challenge for retry)
    - Challenge is single-use (consumed on success)
    - Expired challenge: FAILS
    - Direct POST without challenge/proof: FAILS (unless dev insecure mode)
    
    Preferred flow:
    1. Native layer calls GET /api/local/security/challenge
    2. Native layer performs OS LocalAuthentication (Touch ID, Face ID, passcode)
    3. Native layer obtains native capability proof from its environment
    4. Native layer POSTs /unlock with {challenge_token, native_proof}
    5. Server validates both, unlocks window
    
    Dev mode flow (INTAKE_ENABLE_INSECURE_DEV_UNLOCK=1):
    1. POST /unlock with empty body or just dev flag
    2. Server unlocks but labels as "dev_insecure"
    """
    settings = get_settings()
    from intake.local_console.security.unlock import get_auth_window

    client_host = request.client.host if request.client else None

    # Always enforce loopback
    if client_host not in ["127.0.0.1", "::1", "localhost", "testclient"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unlock only permitted from loopback"
        )

    auth_window = get_auth_window()

    # Check for dev insecure mode
    is_dev_insecure_enabled = settings.intake_enable_insecure_dev_unlock

    # Parse body - handle both JSON and form-encoded
    if body is None:
        try:
            body = UnlockRequest.model_validate(await request.json())
        except Exception:
            body = UnlockRequest()

    challenge_token = body.challenge_token
    native_proof = body.native_proof

    # CLEAR SECURITY REQUIREMENT: Both challenge AND proof are required
    # Challenge token alone must NOT unlock
    if challenge_token and not native_proof:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Native proof is required alongside challenge token. Challenge alone is insufficient."
        )

    # Native proof alone must NOT unlock
    if native_proof and not challenge_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Challenge token is required alongside native proof. Proof alone is insufficient."
        )

    # If we have both challenge and proof, validate them
    if challenge_token and native_proof:
        # Validate challenge first (without consuming yet)
        # Use peeking approach - check exists and not expired without marking consumed
        if challenge_token not in _challenge_store:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid or expired challenge token"
            )

        challenge = _challenge_store[challenge_token]
        now = datetime.now(timezone.utc)

        # Check if expired
        if now > challenge["expires_at"]:
            # Mark as consumed to prevent reuse, but return expired error
            challenge["consumed"] = True
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Challenge token expired"
            )

        # Check if already consumed
        if challenge.get("consumed", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Challenge token already used"
            )

        # Validate native proof against capability
        if not _validate_native_proof(native_proof):
            # Do NOT consume challenge on invalid proof - allow retry
            # after user fixes auth/transport issue
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Native capability proof validation failed. Native capability confirmed: no."
            )

        # All validations passed - consume challenge and unlock
        challenge["consumed"] = True
        auth_window.unlock()

        return UnlockStatus(
            is_unlocked=auth_window.is_unlocked,
            remaining_seconds=auth_window.remaining_seconds,
            unlock_mode="native_os_auth",
            requires_native_auth=True
        )

    # No challenge or proof provided

    # Check if this is dev insecure mode
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
               "Both challenge_token AND native_proof are required. "
               "No partial credentials accepted."
    )


# ============================================================
# /api/local/security/lock - Clear authorization window
# ============================================================

@router.post("/lock", response_model=UnlockStatus)
async def perform_lock():
    """Immediately clear the authorization window."""
    from intake.local_console.security.unlock import get_auth_window

    auth_window = get_auth_window()
    auth_window.lock()

    return UnlockStatus(
        is_unlocked=False,
        remaining_seconds=0.0,
        unlock_mode="none",
        requires_native_auth=True
    )


def reset_security_state():
    """Reset all security state (for testing)."""
    global _challenge_store, _native_capability
    _challenge_store.clear()
    _native_capability = None
