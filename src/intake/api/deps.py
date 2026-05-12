"""Common dependencies for API endpoints."""

from fastapi import Depends, HTTPException, Request

from intake.config import Settings, get_settings
from intake.services.session_service import get_session_service, SessionService
from intake.storage.repositories import AccountRepository


async def get_current_account_id(
    request: Request,
    session_service: SessionService = Depends(get_session_service),
    settings: Settings = Depends(get_settings),
) -> str:
    """Dependency to get the current authenticated account ID.
    
    Raises:
        HTTPException: If not authenticated
    """
    session_id = request.cookies.get(settings.intake_session_cookie_name)

    if session_id:
        session = session_service.get_session_by_id(session_id)
        if session and session.is_active:
            return session.account_id

    raise HTTPException(status_code=401, detail="Not authenticated")


def get_account_repo() -> AccountRepository:
    """Dependency to get an AccountRepository."""
    return AccountRepository()
