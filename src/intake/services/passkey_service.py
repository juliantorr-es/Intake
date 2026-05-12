"""Passkey service for WebAuthn authentication."""

import base64
import secrets
import uuid
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel

try:
    from webauthn import (
        base64url_to_bytes,
        bytes_to_base64url,
        generate_registration_options,
        options_to_json,
        verify_registration_response,
        generate_authentication_options,
        verify_authentication_response,
    )
    from webauthn.helpers.structs import (
        PublicKeyCredentialCreationOptions,
        UserVerificationRequirement,
        AuthenticatorSelectionCriteria,
    )
    from webauthn.helpers.options import COSE
    WEB_AUTHN_AVAILABLE = True
except ImportError:
    # webauthn package not available - create stubs for bootstrap
    WEB_AUTHN_AVAILABLE = False
    COSE = type('COSE', (), {'RS256': -257})()  # Stub for COSE.RS256

from intake.config import get_settings
from intake.domain.accounts import Account
from intake.domain.events import Event, EventActorType, EventType
from intake.domain.passkeys import (
    PasskeyChallenge,
    PasskeyChallengeStatus,
    PasskeyCredential,
    PasskeyRegistrationOptions,
)
from intake.storage.repositories import AccountRepository, EventRepository, PasskeyRepository


class PasskeyService:
    """Service for passkey registration and authentication.

    TODO markers indicate where external browser ceremony integration is required.
    """

    def __init__(
        self,
        account_repo: AccountRepository | None = None,
        passkey_repo: PasskeyRepository | None = None,
        event_repo: EventRepository | None = None,
    ):
        """Initialize passkey service.

        Args:
            account_repo: AccountRepository instance
            passkey_repo: PasskeyRepository instance
            event_repo: EventRepository instance
        """
        self._account_repo = account_repo or AccountRepository()
        self._passkey_repo = passkey_repo or PasskeyRepository()
        self._event_repo = event_repo or EventRepository()
        self._settings = get_settings()

    def get_relying_party_config(self) -> dict[str, str]:
        """Get relying party configuration from settings."""
        return {
            "id": self._settings.intake_rp_id,
            "name": self._settings.intake_rp_name,
        }

    def create_registration_options(self, account: Account | None = None) -> PasskeyRegistrationOptions:
        """Create options for passkey registration.

        TODO: Browser ceremony - this returns options that the browser uses
        to prompt the user to create a passkey.

        Args:
            account: Account to associate with the registration (optional)

        Returns:
            Registration options for the browser
        """
        rp_config = self.get_relying_party_config()
        settings = get_settings()

        # Create a challenge
        challenge = PasskeyChallenge.create_registration_challenge(
            rp_id=rp_config["id"],
            origin=settings.intake_origin,
            account_id=account.id if account else None,
        )

        # Register the challenge (store it for later verification)
        # For now, we just return it - in a real implementation, we'd store it
        # and return a challenge ID that the client uses to complete registration
        # TODO: Store challenge and return only challenge_id to client

        user_id = account.id.encode() if account else secrets.token_bytes(16)

        options = generate_registration_options(
            rp_id=rp_config["id"],
            rp_name=rp_config["name"],
            user_id=user_id,
            user_name=account.id if account else "anonymous",
            user_display_name="New User" if not account else f"User {account.id[:8]}",
        )

        # Convert to our domain model
        return PasskeyRegistrationOptions(
            challenge=challenge.challenge,
            rp={"id": rp_config["id"], "name": rp_config["name"]},
            user={
                "id": base64.urlsafe_b64encode(user_id).decode(),
                "name": account.id if account else "anonymous",
                "displayName": "New User" if not account else f"User {account.id[:8]}",
            },
            pubKeyCredParams=[{"type": "public-key", "alg": COSE.RS256}],
            authenticatorSelection={
                "requireResidentKey": True,
                "userVerification": UserVerificationRequirement.PREFERRED,
            },
            timeout=60000,
        )

    def verify_registration(self, credential: dict[str, Any]) -> PasskeyCredential:
        """Verify a passkey registration response.

        TODO: Browser ceremony - this verifies the response from the browser's
        passkey creation ceremony.

        Args:
            credential: The credential response from the browser

        Returns:
            PasskeyCredential domain model if registration successful

        Raises:
            HTTPException: If verification fails
        """
        settings = get_settings()
        rp_config = self.get_relying_party_config()

        # Find the challenge
        # TODO: Look up challenge by ID from storage
        challenge_str = credential.get("response", {}).get("challenge", "")

        try:
            # Verify the registration
            verification = verify_registration_response(
                credential=credential,
                expected_challenge=challenge_str.encode(),
                expected_rp_id=rp_config["id"],
                expected_origin=settings.intake_origin,
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Registration failed: {e}") from e

        # Extract credential data
        attestation = verification.credential

        # Create or get account
        # For this bootstrap, we'll create a new account
        account = Account()
        self._account_repo.create(account)

        # Create the credential
        passkey_credential = PasskeyCredential(
            credential_id=base64.urlsafe_b64encode(attestation.credential_id).decode(),
            public_key=base64.urlsafe_b64encode(attestation.public_key).decode(),
            counter=0,
            account_id=account.id,
            name=credential.get("name"),
        )

        # Store the credential
        self._passkey_repo.create_credential(passkey_credential)

        # Log the event
        event = Event.for_account(
            account_id=account.id,
            event_type=EventType.PASSKEY_CREDENTIAL_REGISTERED,
            actor_type=EventActorType.ANONYMOUS,
            redacted_summary="Passkey credential registered",
        )
        self._event_repo.append(event)

        return passkey_credential

    def create_authentication_options(self, account_id: str | None = None) -> PasskeyRegistrationOptions:
        """Create options for passkey authentication.

        TODO: Browser ceremony - this returns options that the browser uses
        to prompt the user to authenticate with a passkey.

        Args:
            account_id: Optional account ID hint

        Returns:
            Authentication options for the browser
        """
        settings = get_settings()
        rp_config = self.get_relying_party_config()

        # Create a challenge
        challenge = PasskeyChallenge.create_authentication_challenge(
            rp_id=rp_config["id"],
            origin=settings.intake_origin,
            account_id=account_id,
        )

        # TODO: Store challenge and return only challenge_id

        options = generate_authentication_options(
            rp_id=rp_config["id"],
        )

        # Convert to our domain model (reusing PasskeyRegistrationOptions for convenience)
        return PasskeyRegistrationOptions(
            challenge=challenge.challenge,
            rp={"id": rp_config["id"], "name": rp_config["name"]},
            user={},  # User info not needed for authentication
            pubKeyCredParams=[{"type": "public-key", "alg": COSE.RS256}],
        )

    def verify_authentication(self, credential: dict[str, Any]) -> Account:
        """Verify a passkey authentication response.

        TODO: Browser ceremony - this verifies the response from the browser's
        passkey authentication ceremony.

        Args:
            credential: The credential response from the browser

        Returns:
            Account if authentication successful

        Raises:
            HTTPException: If authentication fails
        """
        settings = get_settings()
        rp_config = self.get_relying_party_config()

        credential_id_b64 = credential.get("id", "")
        credential_id = base64url_to_bytes(credential_id_b64)

        try:
            # Find the credential
            passkey_cred = self._passkey_repo.get_credential(credential_id_b64)
            if not passkey_cred:
                raise ValueError("Credential not found")

            # Get the account
            account = self._account_repo.get_by_id(passkey_cred.account_id)
            if not account:
                raise ValueError("Account not found")

            # Verify the authentication
            verification = verify_authentication_response(
                credential=credential,
                expected_challenge=credential.get("response", {}).get("challenge", "").encode(),
                expected_rp_id=rp_config["id"],
                expected_origin=settings.intake_origin,
                credential_public_key=base64url_to_bytes(passkey_cred.public_key),
                credential_current_sign_count=passkey_cred.counter,
            )

            # Update the counter
            new_counter = verification.new_sign_count
            self._passkey_repo.update_credential_counter(passkey_cred.id, int(new_counter))

            # Log the event
            event = Event.for_account(
                account_id=account.id,
                event_type=EventType.PASSKEY_AUTHENTICATION_SUCCESS,
                actor_type=EventActorType.ACCOUNT,
                actor_id=account.id,
                redacted_summary="Passkey authentication successful",
            )
            self._event_repo.append(event)

            return account

        except Exception as e:
            # Log failure event
            event = Event.for_account(
                account_id=passkey_cred.account_id if passkey_cred else "unknown",
                event_type=EventType.PASSKEY_AUTHENTICATION_FAILURE,
                actor_type=EventActorType.ANONYMOUS,
                redacted_summary=f"Authentication failed: {type(e).__name__}",
            )
            self._event_repo.append(event)
            raise HTTPException(status_code=401, detail=f"Authentication failed: {e}") from e

    def invalidate_challenge(self, challenge_id: str) -> bool:
        """Invalidate a challenge (mark as consumed).

        Args:
            challenge_id: ID of the challenge to invalidate

        Returns:
            True if challenge was found and invalidated
        """
        # TODO: Implement challenge storage and invalidation
        return True


@lru_cache()
def get_passkey_service() -> PasskeyService:
    """Get cached passkey service instance."""
    return PasskeyService()


def reset_passkey_service() -> None:
    """Reset the cached passkey service (useful for testing)."""
    get_passkey_service.cache_clear()
