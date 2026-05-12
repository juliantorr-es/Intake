from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from intake.local_console.security.unlock import get_auth_window, LocalAuthorizationWindow

router = APIRouter(prefix="/security", tags=["security"])

class UnlockStatus(BaseModel):
    is_unlocked: bool
    remaining_seconds: float

@router.get("/status", response_model=UnlockStatus)
async def get_unlock_status(
    auth_window: LocalAuthorizationWindow = Depends(get_auth_window)
):
    """Get the current secure unlock status."""
    return UnlockStatus(
        is_unlocked=auth_window.is_unlocked,
        remaining_seconds=auth_window.remaining_seconds
    )

@router.post("/unlock", response_model=UnlockStatus)
async def perform_unlock(
    request: Request,
    auth_window: LocalAuthorizationWindow = Depends(get_auth_window)
):
    """Refine the authorization window (called by native shell).
    
    Security: This endpoint should only be reachable via loopback.
    """
    # Verify we are on loopback
    client_host = request.client.host if request.client else None
    if client_host not in ["127.0.0.1", "::1", "localhost"]:
         # This should be blocked by server binding anyway, but defense in depth
         raise HTTPException(status_code=403, detail="Unlock only permitted from loopback")
         
    auth_window.unlock()
    return UnlockStatus(
        is_unlocked=auth_window.is_unlocked,
        remaining_seconds=auth_window.remaining_seconds
    )

@router.post("/lock", response_model=UnlockStatus)
async def perform_lock(
    auth_window: LocalAuthorizationWindow = Depends(get_auth_window)
):
    """Immediately clear the authorization window."""
    auth_window.lock()
    return UnlockStatus(
        is_unlocked=False,
        remaining_seconds=0.0
    )
