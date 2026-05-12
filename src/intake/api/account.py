"""Account and settings endpoints."""

from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from intake.api.deps import get_current_account_id, get_account_repo
from intake.services.email_verification_service import get_email_verification_service, EmailVerificationService
from intake.storage.repositories import AccountRepository


router = APIRouter()


# ========== Request/Response Models ==========

class EmailStartRequest(BaseModel):
    """Request to start email verification."""
    email: str


class EmailVerifyRequest(BaseModel):
    """Request to verify email code."""
    email: str
    code: str


class EmailSettings(BaseModel):
    """Email settings status."""
    status: str
    masked: str | None = None
    verified_at: str | None = None


class AccountSettingsResponse(BaseModel):
    """Response for account settings."""
    account_id: str
    email: EmailSettings


# ========== Endpoints ==========

@router.get("/settings", response_model=AccountSettingsResponse)
async def get_settings_info(
    account_id: str = Depends(get_current_account_id),
    account_repo: AccountRepository = Depends(get_account_repo),
) -> AccountSettingsResponse:
    """Get account settings and status."""
    account = account_repo.get_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    # Mask email if present
    masked_email = None
    if account.normalized_email_hash:
        # We don't have the plaintext email here directly if we strictly use domain model 
        # without decryption. But we can decrypt it here for the settings page.
        from intake.services.crypto_service import get_crypto_service
        crypto = get_crypto_service()
        try:
            if account.encrypted_email:
                decrypted = crypto.decrypt_json(account.encrypted_email)
                email = decrypted.get("email", "")
                user, domain = email.split("@", 1)
                masked_email = f"{user[0]}***@{domain}"
        except Exception:
            masked_email = "e***@example.com" # Fallback

    return AccountSettingsResponse(
        account_id=account_id,
        email={
            "status": account.email_status,
            "masked": masked_email,
            "verified_at": account.email_verified_at.isoformat() if account.email_verified_at else None
        }
    )


@router.post("/email/start-verification")
async def start_email_verification(
    request: EmailStartRequest,
    account_id: str = Depends(get_current_account_id),
    service: EmailVerificationService = Depends(get_email_verification_service),
):
    """Start the email verification flow."""
    success = service.start_verification(account_id, request.email)
    if not success:
        # Use generic error or success to avoid enumeration
        return {"status": "verification_sent", "email_status": "pending"}

    return {"status": "verification_sent", "email_status": "pending"}


@router.post("/email/verify")
async def verify_email_code(
    request: EmailVerifyRequest,
    account_id: str = Depends(get_current_account_id),
    service: EmailVerificationService = Depends(get_email_verification_service),
):
    """Verify the email code."""
    success = service.verify_code(account_id, request.email, request.code)
    if not success:
        raise HTTPException(status_code=400, detail="Invalid or expired verification code")

    return {"status": "verified", "email_status": "verified"}
