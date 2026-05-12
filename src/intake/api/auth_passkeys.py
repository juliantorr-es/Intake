"""Passkey authentication endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from intake.domain.passkeys import PasskeyRegistrationOptions
from intake.services.passkey_service import get_passkey_service, PasskeyService

router = APIRouter(prefix="/passkey")


class PasskeyRegisterOptionsRequest(BaseModel):
    """Request for registration options."""

    pass


class PasskeyRegisterOptionsResponse(BaseModel):
    """Response with registration options."""

    options: PasskeyRegistrationOptions


class PasskeyRegisterVerifyRequest(BaseModel):
    """Request to verify registration."""

    credential: dict


class PasskeyRegisterVerifyResponse(BaseModel):
    """Response for registration verification."""

    success: bool
    account_id: str | None = None


class PasskeyLoginOptionsRequest(BaseModel):
    """Request for login options."""

    pass


class PasskeyLoginOptionsResponse(BaseModel):
    """Response with login options."""

    options: PasskeyRegistrationOptions


class PasskeyLoginVerifyRequest(BaseModel):
    """Request to verify login."""

    credential: dict


class PasskeyLoginVerifyResponse(BaseModel):
    """Response for login verification."""

    success: bool
    account_id: str | None = None
    session_token: str | None = None


class SessionResponse(BaseModel):
    """Session information response."""

    authenticated: bool
    account_id: str | None = None


class LogoutResponse(BaseModel):
    """Logout response."""

    success: bool


@router.post("/register/options", response_model=PasskeyRegisterOptionsResponse)
async def register_options(
    request: PasskeyRegisterOptionsRequest,
    service: PasskeyService = Depends(get_passkey_service),
) -> PasskeyRegisterOptionsResponse:
    """Get options for passkey registration.

    Returns the registration options that the browser uses to prompt
    the user to create a passkey.
    """
    options = service.create_registration_options()
    return PasskeyRegisterOptionsResponse(options=options)


@router.post("/register/verify", response_model=PasskeyRegisterVerifyResponse)
async def register_verify(
    request: PasskeyRegisterVerifyRequest,
    service: PasskeyService = Depends(get_passkey_service),
) -> PasskeyRegisterVerifyResponse:
    """Verify a passkey registration.

    This endpoint verifies the response from the browser's passkey
    creation ceremony.
    """
    try:
        credential = service.verify_registration(request.credential)
        return PasskeyRegisterVerifyResponse(
            success=True,
            account_id=credential.account_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login/options", response_model=PasskeyLoginOptionsResponse)
async def login_options(
    request: PasskeyLoginOptionsRequest,
    service: PasskeyService = Depends(get_passkey_service),
) -> PasskeyLoginOptionsResponse:
    """Get options for passkey login.

    Returns the authentication options that the browser uses to prompt
    the user to authenticate with a passkey.
    """
    options = service.create_authentication_options()
    return PasskeyLoginOptionsResponse(options=options)


@router.post("/login/verify", response_model=PasskeyLoginVerifyResponse)
async def login_verify(
    request: PasskeyLoginVerifyRequest,
    service: PasskeyService = Depends(get_passkey_service),
) -> PasskeyLoginVerifyResponse:
    """Verify a passkey login.

    This endpoint verifies the response from the browser's passkey
    authentication ceremony.
    """
    try:
        account = service.verify_authentication(request.credential)
        # TODO: Create a session token
        return PasskeyLoginVerifyResponse(
            success=True,
            account_id=account.id,
            session_token="todo-session-token",  # TODO: Generate real session token
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/logout", response_model=LogoutResponse)
async def logout() -> LogoutResponse:
    """Logout and invalidate session.

    TODO: Implement actual session invalidation.
    """
    # TODO: Invalidate the session
    return LogoutResponse(success=True)


@router.get("/session", response_model=SessionResponse)
async def get_session() -> SessionResponse:
    """Get current session information.

    TODO: Implement actual session lookup.
    """
    # TODO: Look up session from request
    return SessionResponse(
        authenticated=False,
        account_id=None,
    )
