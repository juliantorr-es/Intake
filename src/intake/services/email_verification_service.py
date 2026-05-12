"""Service for email verification logic."""

import hashlib
import random
import string
from datetime import timedelta
from typing import Any

from intake.config import get_settings
from intake.domain.accounts import Account, EmailVerificationCode
from intake.domain.events import EventActorType, EventType
from intake.domain.time import utc_now, utc_expires_in
from intake.services.crypto_service import get_crypto_service
from intake.services.email_sender import get_email_sender, EmailSender
from intake.services.event_log import get_event_log_service
from intake.storage.repositories import AccountRepository, EmailVerificationRepository


class EmailVerificationService:
    """Service for managing email verification flow."""

    def __init__(
        self,
        account_repo: AccountRepository | None = None,
        verification_repo: EmailVerificationRepository | None = None,
        email_sender: EmailSender | None = None,
        crypto_service: Any | None = None,
        event_log: Any | None = None,
    ):
        self._account_repo = account_repo or AccountRepository()
        self._verification_repo = verification_repo or EmailVerificationRepository()
        self._email_sender = email_sender or get_email_sender()
        self._crypto = crypto_service or get_crypto_service()
        self._event_log = event_log or get_event_log_service()
        self._settings = get_settings()

    def _normalize_email(self, email: str) -> str:
        """Normalize email address."""
        return email.strip().lower()

    def _hash_email(self, email: str) -> str:
        """Hash normalized email for deduplication/lookup."""
        normalized = self._normalize_email(email)
        # Use a stable hash for lookup
        return hashlib.sha256(normalized.encode()).hexdigest()

    def _hash_code(self, code: str) -> str:
        """Hash verification code for storage."""
        return hashlib.sha256(code.encode()).hexdigest()

    def _generate_code(self, length: int = 6) -> str:
        """Generate a numeric verification code."""
        return "".join(random.choices(string.digits, k=length))

    def start_verification(self, account_id: str, email: str) -> bool:
        """Start email verification flow."""
        normalized_email = self._normalize_email(email)
        email_hash = self._hash_email(normalized_email)
        
        # Check if email is already verified by another account
        existing_account = self._account_repo.get_by_email_hash(email_hash)
        if existing_account and existing_account.id != account_id and existing_account.email_verified_at:
            # Silent failure to avoid email enumeration
            # Still generate a code for the requester to maintain timing
            pass

        account = self._account_repo.get_by_id(account_id)
        if not account:
            return False

        # Generate and store code
        code_raw = self._generate_code()
        code_hash = self._hash_code(code_raw)
        
        ttl = self._settings.intake_email_code_ttl_seconds
        max_attempts = self._settings.intake_email_code_max_attempts
        
        # Invalidate any existing active codes for this email/account
        # (This is optional but prevents code accumulation)

        verification_code = EmailVerificationCode(
            account_id=account_id,
            email_hash=email_hash,
            code_hash=code_hash,
            max_attempts=max_attempts,
            expires_at=utc_now() + timedelta(seconds=ttl)
        )
        self._verification_repo.create(verification_code)

        # Update account with pending email (encrypted)
        account.encrypted_email = self._crypto.encrypt_json({"email": normalized_email})
        account.normalized_email_hash = email_hash
        # Important: Don't clear email_verified_at yet if it was already verified 
        # (though usually we'd only allow change if re-verifying)
        self._account_repo.update(account)

        # Send email
        self._email_sender.send_verification_email(normalized_email, code_raw)

        # Log event
        self._event_log.append_account_event(
            account=account,
            event_type=EventType.ACCOUNT_EMAIL_VERIFICATION_SENT,
            actor_type=EventActorType.ACCOUNT,
            actor_id=account_id,
            redacted_summary=f"Verification email sent to {self._mask_email(normalized_email)}"
        )

        return True

    def verify_code(self, account_id: str, email: str, code: str) -> bool:
        """Verify the code and mark email as verified."""
        normalized_email = self._normalize_email(email)
        email_hash = self._hash_email(normalized_email)
        code_hash = self._hash_code(code)

        codes = self._verification_repo.get_active_by_email_hash(email_hash)
        # Filter for this account
        codes = [c for c in codes if c.account_id == account_id]
        
        if not codes:
            return False

        # We take the most recent one or check all active ones
        # For simplicity, we check all active ones
        target_code = None
        for c in codes:
            if c.code_hash == code_hash:
                target_code = c
                break
        
        if not target_code:
            # Increment attempts for all active codes for this email/account
            for c in codes:
                c.attempts += 1
                self._verification_repo.update(c)
            return False

        if not target_code.can_attempt:
            return False

        # Success!
        target_code.consumed_at = utc_now()
        self._verification_repo.update(target_code)

        account = self._account_repo.get_by_id(account_id)
        if account:
            account.email_verified_at = utc_now()
            self._account_repo.update(account)

            # Log event
            self._event_log.append_account_event(
                account=account,
                event_type=EventType.ACCOUNT_EMAIL_VERIFIED,
                actor_type=EventActorType.ACCOUNT,
                actor_id=account_id,
                redacted_summary=f"Email {self._mask_email(normalized_email)} verified"
            )

        return True

    def _mask_email(self, email: str) -> str:
        """Mask email address for logs/summaries."""
        if "@" not in email:
            return "***"
        user, domain = email.split("@", 1)
        if len(user) <= 1:
            return f"*@{domain}"
        return f"{user[0]}***@{domain}"


def get_email_verification_service() -> EmailVerificationService:
    """Get email verification service instance."""
    return EmailVerificationService()
