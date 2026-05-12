"""Passkey authentication endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, Cookie
from pydantic import BaseModel

from intake.config import Settings, get_settings
from intake.domain.passkeys import PasskeyRegistrationOptions
from intake.services.passkey_service import get_passkey_service, PasskeyService
from intake.services.session_service import get_session_service, SessionService

router = APIRouter(prefix="/passkey")


class PasskeyRegisterOptionsRequest(BaseModel):
    """Request for registration options."""

    model_config = {"extra": "forbid"}


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

    model_config = {"extra": "forbid"}


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


class SessionResponse(BaseModel):
    """Session information response."""

    authenticated: bool
    account_id: str | None = None


class LogoutResponse(BaseModel):
    """Logout response."""

    success: bool


@router.post("/register/options", response_model=PasskeyRegisterOptionsResponse)
async def register_options(
    request: PasskeyRegisterOptionsRequest | None = None,
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
        credential, account = service.verify_registration(request.credential)
        return PasskeyRegisterVerifyResponse(
            success=True,
            account_id=account.id,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login/options", response_model=PasskeyLoginOptionsResponse)
async def login_options(
    request: PasskeyLoginOptionsRequest | None = None,
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
    response: Response,
    service: PasskeyService = Depends(get_passkey_service),
) -> PasskeyLoginVerifyResponse:
    """Verify a passkey login.

    This endpoint verifies the response from the browser's passkey
    authentication ceremony and creates a session.
    """
    try:
        account, session_id = service.verify_authentication(request.credential)

        # Get the session token from the session service
        # The session service stores only the hash, we need to generate the token
        session_service = get_session_service()
        session = session_service.get_session_by_id(session_id)
        settings = get_settings()

        if session:
            # Set the session token as a secure cookie
            # We return the session_id as the token reference
            # In production, this would be a proper JWT or similar
            response.set_cookie(
                key=settings.intake_session_cookie_name,
                value=session_id,
                httponly=settings.intake_session_cookie_httponly,
                secure=settings.session_cookie_secure,
                samesite=settings.intake_session_cookie_samesite,
                max_age=settings.intake_session_ttl_seconds,
            )
            return PasskeyLoginVerifyResponse(
                success=True,
                account_id=account.id,
            )
        else:
            raise HTTPException(status_code=500, detail="Session not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    request: Request,
    response: Response,
    session_service: SessionService = Depends(get_session_service),
    settings: Settings = Depends(get_settings),
) -> LogoutResponse:
    """Logout and invalidate session.

    Clears the session cookie and revokes the session on the server.
    """
    # Get session ID from cookie
    session_id = request.cookies.get(settings.intake_session_cookie_name)

    if session_id:
        # Revoke the session
        session_service.revoke_session(session_id)

        # Clear the cookie
        response.delete_cookie(
            key=settings.intake_session_cookie_name,
            httponly=settings.intake_session_cookie_httponly,
            secure=settings.session_cookie_secure,
            samesite=settings.intake_session_cookie_samesite,
        )

    return LogoutResponse(success=True)


@router.get("/session", response_model=SessionResponse)
async def get_session(
    request: Request,
    session_service: SessionService = Depends(get_session_service),
    settings: Settings = Depends(get_settings),
) -> SessionResponse:
    """Get current session information.

    Checks the session cookie and returns the authenticated state.
    """
    session_id = request.cookies.get(settings.intake_session_cookie_name)

    if session_id:
        session = session_service.get_session_by_id(session_id)
        if session and session.is_active:
            return SessionResponse(
                authenticated=True,
                account_id=session.account_id,
            )

    return SessionResponse(
        authenticated=False,
        account_id=None,
    )
