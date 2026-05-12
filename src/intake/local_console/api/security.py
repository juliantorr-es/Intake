"""Local Console Security API for step-up authorization."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from intake.local_console.security.unlock import get_auth_window, UnlockStatus

router = APIRouter(prefix="/security")


@router.get("/status", response_model=UnlockStatus)
async def get_security_status():
    """Get the current local authorization status.
    
    This indicates if the operator has recently performed a Local Secure Unlock.
    """
    return get_auth_window().get_status()


@router.post("/unlock", response_model=UnlockStatus)
async def post_unlock():
    """Create or refresh the local authorization window.
    
    This endpoint should only be called after the native shell (SwiftUI)
    has successfully verified the operator via LocalAuthentication.
    """
    window = get_auth_window()
    window.unlock()
    return window.get_status()


@router.post("/lock", response_model=UnlockStatus)
async def post_lock():
    """Immediately clear the local authorization window."""
    window = get_auth_window()
    window.lock()
    return window.get_status()
