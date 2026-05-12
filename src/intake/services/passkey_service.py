"""Passkey service for WebAuthn authentication.

Uses Duo Labs py_webauthn library (package: webauthn)
See: https://github.com/duo-labs/py_webauthn
"""

import base64
import secrets
import uuid
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel

from intake.domain.time import utc_now

# Duo Labs py_webauthn (package: webauthn)
# See: https://github.com/duo-labs/py_webauthn
from webauthn import (
    base64url_to_bytes,
    generate_registration_options,
    options_to_json,
    verify_registration_response,
    generate_authentication_options,
    verify_authentication_response,
)
from webauthn.helpers import bytes_to_base64url
from webauthn.helpers.structs import (
    PublicKeyCredentialCreationOptions,
    UserVerificationRequirement,
    AuthenticatorSelectionCriteria,
    AttestationConveyancePreference,
    ResidentKeyRequirement,
    PublicKeyCredentialDescriptor,
    AuthenticatorTransport,
)
from webauthn.helpers.cose import COSEAlgorithmIdentifier

from intake.config import get_settings
from intake.domain.accounts import Account
from intake.domain.events import Event, EventActorType, EventType
from intake.domain.passkeys import (
    ChallengeAction,
    PasskeyChallenge,
    PasskeyChallengeStatus,
    PasskeyCredential,
    PasskeyRegistrationOptions,
)
from intake.services.crypto_service import get_crypto_service
from intake.services.session_service import get_session_service
from intake.storage.repositories import (
    AccountRepository,
    ChallengeRepository,
    EventRepository,
    PasskeyRepository,
)
from intake.storage.models import PasskeyChallengeModel, PasskeyCredentialModel


# Session expiry for passkey authentication sessions (shorter than full sessions)
PASSKEY_SESSION_EXPIRY_SECONDS = 300  # 5 minutes


class PasskeyService:
    """Service for passkey registration and authentication.

    This service handles:
    - Creating and storing WebAuthn challenges for registration/login
    - Verifying registration and authentication responses
    - Managing passkey credentials
    - Creating sessions on successful authentication
    """

    def __init__(
        self,
        account_repo: AccountRepository | None = None,
        passkey_repo: PasskeyRepository | None = None,
        challenge_repo: ChallengeRepository | None = None,
        event_repo: EventRepository | None = None,
    ):
        """Initialize passkey service.

        Args:
            account_repo: AccountRepository instance
            passkey_repo: PasskeyRepository instance
            challenge_repo: ChallengeRepository instance
            event_repo: EventRepository instance
        """
        self._account_repo = account_repo or AccountRepository()
        self._passkey_repo = passkey_repo or PasskeyRepository()
        self._challenge_repo = challenge_repo or ChallengeRepository()
        self._event_repo = event_repo or EventRepository()
        self._settings = get_settings()

    def get_relying_party_config(self) -> dict[str, str]:
        """Get relying party configuration from settings."""
        return {
            "id": self._settings.intake_rp_id,
            "name": self._settings.intake_rp_name,
        }

    def _store_challenge(self, challenge: PasskeyChallenge) -> PasskeyChallenge:
        """Store a challenge in the database."""
        return self._challenge_repo.create(challenge)

    def create_registration_options(self, account: Account | None = None) -> PasskeyRegistrationOptions:
        """Create options for passkey registration.

        This creates a new challenge record, stores it, and returns options
        that the browser uses to prompt the user to create a passkey.

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

        # Store the challenge
        stored_challenge = self._store_challenge(challenge)

        # Generate user ID for WebAuthn
        user_id = account.id.encode() if account else secrets.token_bytes(16)

        # Specify supported algorithms for WebAuthn
        supported_algs = [
            COSEAlgorithmIdentifier.RSASSA_PKCS1_v1_5_SHA_256,
            COSEAlgorithmIdentifier.ECDSA_SHA_256,
            COSEAlgorithmIdentifier.RSASSA_PSS_SHA_256,
        ]

        options = generate_registration_options(
            rp_id=rp_config["id"],
            rp_name=rp_config["name"],
            user_id=user_id,
            user_name=account.id if account else "anonymous",
            user_display_name="New User" if not account else f"User {account.id[:8]}",
            supported_pub_key_algs=supported_algs,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=AuthenticatorSelectionCriteria.ResidentKeyRequirement.REQUIRED,
                user_verification=UserVerificationRequirement.PREFERRED,
            ),
            attestation=AttestationConveyancePreference.NONE,
        )

        # Convert to our domain model
        return PasskeyRegistrationOptions(
            challenge=stored_challenge.challenge,
            rp={"id": rp_config["id"], "name": rp_config["name"]},
            user={
                "id": base64.urlsafe_b64encode(user_id).decode(),
                "name": account.id if account else "anonymous",
                "displayName": "New User" if not account else f"User {account.id[:8]}",
            },
            pubKeyCredParams=[{"type": "public-key", "alg": -257}],  # ES256 / RSASSA_PKCS1_v1_5_SHA_256
            authenticatorSelection={
                "requireResidentKey": True,
                "userVerification": "preferred",
            },
            timeout=60000,
        )

    def _find_challenge_for_verification(
        self, challenge_value: str, expected_action: ChallengeAction
    ) -> PasskeyChallengeModel | None:
        """Find a challenge by its value and verify it matches the expected action."""
        model = self._challenge_repo.get_by_challenge_value(challenge_value)
        if model is None:
            return None

        # Verify the action matches
        if model.action != expected_action:
            return None

        return model

    def verify_registration(self, credential_data: dict[str, Any]) -> tuple[PasskeyCredential, Account]:
        """Verify a passkey registration response.

        This verifies the response from the browser's passkey creation ceremony
        and creates a new account and credential if successful.

        Args:
            credential_data: The credential response from the browser

        Returns:
            Tuple of (PasskeyCredential, Account) if registration successful

        Raises:
            HTTPException: If verification fails
        """
        settings = get_settings()
        rp_config = self.get_relying_party_config()

        # Extract challenge from credential response
        client_data = credential_data.get("response", {}).get("clientDataJSON", {})
        # The challenge is embedded in clientDataJSON by the browser
        import json
        try:
            client_data_parsed = json.loads(client_data) if isinstance(client_data, str) else client_data
            challenge_value = client_data_parsed.get("challenge", "")
        except (json.JSONDecodeError, AttributeError):
            challenge_value = ""

        # Find the challenge
        challenge_model = self._find_challenge_for_verification(
            challenge_value, ChallengeAction.REGISTER
        )

        if challenge_model is None:
            raise HTTPException(
                status_code=400,
                detail="Invalid or missing challenge",
            )

        # Verify the challenge is still valid
        if challenge_model.status != PasskeyChallengeStatus.PENDING:
            raise HTTPException(
                status_code=400,
                detail="Challenge already used or expired",
            )

        if utc_now() > challenge_model.expires_at:
            # Mark as expired and reject
            self._challenge_repo.mark_consumed(challenge_model.id)
            raise HTTPException(
                status_code=400,
                detail="Challenge expired",
            )

        try:
            # Verify the registration
            verification = verify_registration_response(
                credential=credential_data,
                expected_challenge=base64url_to_bytes(challenge_value),
                expected_rp_id=rp_config["id"],
                expected_origin=settings.intake_origin,
            )
        except Exception as e:
            # Increment attempt count and reject
            self._challenge_repo.increment_attempt(challenge_model.id)
            raise HTTPException(status_code=400, detail=f"Registration failed: {e}") from e

        # Extract credential data from verification
        attestation = verification.credential

        # Create or get account
        # For this bootstrap, we'll create a new account if not provided
        if challenge_model.account_id:
            account = self._account_repo.get_by_id(challenge_model.account_id)
            if not account:
                account = Account(id=challenge_model.account_id)
                self._account_repo.create(account)
        else:
            account = Account()
            self._account_repo.create(account)

        # Create the credential
        credential = PasskeyCredential(
            credential_id=base64.urlsafe_b64encode(attestation.credential_id).decode(),
            public_key=base64.urlsafe_b64encode(attestation.public_key).decode(),
            sign_count=0,
            account_id=account.id,
            name=credential_data.get("name"),
            # Extract WebAuthn metadata
            transports=json.dumps(getattr(attestation, 'transports', [])),
            backup_eligible=getattr(attestation, 'backup_eligible', False),
            backup_state=getattr(attestation, 'backup_state', False),
            device_label=getattr(attestation, 'device_label', None),
        )

        # Store the credential
        self._passkey_repo.create_credential(credential)

        # Mark challenge as consumed
        self._challenge_repo.mark_consumed(challenge_model.id)

        # Log the event
        event = Event.for_account(
            account_id=account.id,
            event_type=EventType.PASSKEY_CREDENTIAL_REGISTERED,
            actor_type=EventActorType.ANONYMOUS,
            redacted_summary="Passkey credential registered",
        )
        self._event_repo.append(event)

        return credential, account

    def create_authentication_options(self, account_id: str | None = None) -> PasskeyRegistrationOptions:
        """Create options for passkey authentication.

        This creates a new challenge record, stores it, and returns options
        that the browser uses to prompt the user to authenticate with a passkey.

        Args:
            account_id: Optional account ID hint

        Returns:
            Authentication options for the browser
        """
        settings = get_settings()
        rp_config = self.get_relying_party_config()

        # Get account if provided
        account = None
        if account_id:
            account = self._account_repo.get_by_id(account_id)

        # Create a challenge
        challenge = PasskeyChallenge.create_authentication_challenge(
            rp_id=rp_config["id"],
            origin=settings.intake_origin,
            account_id=account_id,
        )

        # Store the challenge
        stored_challenge = self._store_challenge(challenge)

        # Generate options for authentication
        # For authentication, we need to specify which credentials are allowed
        # Get all active credentials for the account
        allowed_credentials = []
        if account:
            credentials = self._passkey_repo.get_active_credentials_by_account(account.id)
            for cred in credentials:
                cred_id_bytes = base64.urlsafe_b64decode(cred.credential_id.encode())
                # Parse transports from stored JSON
                import json as json_mod
                transports = None
                if cred.transports:
                    try:
                        transports = [getattr(AuthenticatorTransport, t.upper(), t) for t in json_mod.loads(cred.transports)]
                    except (json_mod.JSONDecodeError, AttributeError):
                        transports = None
                allowed_credentials.append(
                    PublicKeyCredentialDescriptor(
                        id=cred_id_bytes,
                        type="public-key",
                        transports=transports,
                    )
                )

        options = generate_authentication_options(
            rp_id=rp_config["id"],
            allow_credentials=allowed_credentials or None,
            user_verification=UserVerificationRequirement.PREFERRED,
        )

        # Convert to our domain model (reusing PasskeyRegistrationOptions for convenience)
        return PasskeyRegistrationOptions(
            challenge=stored_challenge.challenge,
            rp={"id": rp_config["id"], "name": rp_config["name"]},
            user={},  # User info not needed for authentication
            pubKeyCredParams=[{"type": "public-key", "alg": -257}],
        )

    def verify_authentication(self, credential_data: dict[str, Any]) -> tuple[Account, str]:
        """Verify a passkey authentication response.

        This verifies the response from the browser's passkey authentication ceremony.
        On success, creates a new session and returns the account with session token.

        Args:
            credential_data: The credential response from the browser

        Returns:
            Tuple of (Account, session_token) if authentication successful

        Raises:
            HTTPException: If authentication fails
        """
        import json

        settings = get_settings()
        rp_config = self.get_relying_party_config()

        # Extract challenge from credential response
        client_data = credential_data.get("response", {}).get("clientDataJSON", {})
        try:
            client_data_parsed = json.loads(client_data) if isinstance(client_data, str) else client_data
            challenge_value = client_data_parsed.get("challenge", "")
        except (json.JSONDecodeError, AttributeError):
            challenge_value = ""

        # Find the challenge
        challenge_model = self._find_challenge_for_verification(
            challenge_value, ChallengeAction.LOGIN
        )

        if challenge_model is None:
            raise HTTPException(
                status_code=400,
                detail="Invalid or missing challenge",
            )

        # Verify the challenge is still valid
        if challenge_model.status != PasskeyChallengeStatus.PENDING:
            raise HTTPException(
                status_code=400,
                detail="Challenge already used or expired",
            )

        if utc_now() > challenge_model.expires_at:
            # Mark as expired and reject
            self._challenge_repo.mark_consumed(challenge_model.id)
            raise HTTPException(
                status_code=400,
                detail="Challenge expired",
            )

        # Get the credential ID from the response
        credential_id_b64 = credential_data.get("id", "")

        try:
            credential_id_bytes = base64url_to_bytes(credential_id_b64)
        except Exception:
            self._challenge_repo.increment_attempt(challenge_model.id)
            raise HTTPException(status_code=400, detail="Invalid credential ID format")

        # Find the credential
        credential_model = self._passkey_repo.get_credential(credential_id_b64)
        if not credential_model:
            self._challenge_repo.increment_attempt(challenge_model.id)
            raise HTTPException(status_code=400, detail="Credential not found")

        # Get the account
        account = self._account_repo.get_by_id(credential_model.account_id)
        if not account:
            self._challenge_repo.increment_attempt(challenge_model.id)
            raise HTTPException(status_code=400, detail="Account not found")

        try:
            # Verify the authentication
            public_key_bytes = base64.urlsafe_b64decode(credential_model.public_key.encode())

            verification = verify_authentication_response(
                credential=credential_data,
                expected_challenge=base64url_to_bytes(challenge_value),
                expected_rp_id=rp_config["id"],
                expected_origin=settings.intake_origin,
                credential_public_key=public_key_bytes,
                credential_current_sign_count=credential_model.sign_count,
            )

            # Update the credential's sign count
            new_sign_count = verification.new_sign_count
            self._passkey_repo.update_after_login(credential_model.id, int(new_sign_count))

            # Mark challenge as consumed
            self._challenge_repo.mark_consumed(challenge_model.id)

            # Create a new session
            session_service = get_session_service()
            session = session_service.create_session(account.id)

            # Log the event
            event = Event.for_account(
                account_id=account.id,
                event_type=EventType.PASSKEY_AUTHENTICATION_SUCCESS,
                actor_type=EventActorType.ACCOUNT,
                actor_id=account.id,
                redacted_summary="Passkey authentication successful",
            )
            self._event_repo.append(event)

            return account, session.id

        except Exception as e:
            # Log failure event
            self._challenge_repo.increment_attempt(challenge_model.id)
            event = Event.for_account(
                account_id=credential_model.account_id,
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
        return self._challenge_repo.mark_consumed(challenge_id)

    def get_account_by_credential(self, credential_id: str) -> Account | None:
        """Get the account associated with a credential.

        Args:
            credential_id: The credential ID

        Returns:
            Account if found, None otherwise
        """
        credential_model = self._passkey_repo.get_credential(credential_id)
        if credential_model:
            return self._account_repo.get_by_id(credential_model.account_id)
        return None


@lru_cache()
def get_passkey_service() -> PasskeyService:
    """Get cached passkey service instance."""
    return PasskeyService()


def reset_passkey_service() -> None:
    """Reset the cached passkey service (useful for testing)."""
    get_passkey_service.cache_clear()
