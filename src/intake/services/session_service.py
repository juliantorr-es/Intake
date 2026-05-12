"""Session service for managing authentication sessions."""

import hashlib
import secrets
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any

from intake.config import get_settings
from intake.domain.accounts import Session as SessionDomain
from intake.domain.time import utc_now
from intake.services.crypto_service import get_crypto_service
from intake.storage.repositories import SessionRepository


class SessionService:
    """Service for session management.

    Sessions are:
    - Created with a unique token (32-byte random)
    - Only the SHA-256 hash of the token is stored in the database
    - The raw token is returned to the client once (via secure cookie)
    - Looked up by hash when validating
    - Revoked by setting revoked_at timestamp
    """

    def __init__(
        self,
        repository: SessionRepository | None = None,
    ):
        """Initialize session service.

        Args:
            repository: SessionRepository instance
        """
        self._repo = repository or SessionRepository()
        settings = get_settings()
        self._session_expiry = settings.intake_session_ttl_seconds

    def generate_token(self) -> str:
        """Generate a new session token (32-byte URL-safe base64).

        Returns:
            A new unique session token string
        """
        return secrets.token_urlsafe(32)

    @staticmethod
    def hash_token(token: str) -> str:
        """Hash a session token for storage.

        Uses SHA-256 with a purpose prefix to prevent collision attacks.

        Args:
            token: The raw session token

        Returns:
            Hex-encoded SHA-256 hash
        """
        combined = f"session_token|{token}"
        return hashlib.sha256(combined.encode()).hexdigest()

    def create_session(self, account_id: str, token: str | None = None) -> SessionDomain:
        """Create a new session for an account.

        Args:
            account_id: The account ID to associate with the session
            token: Optional pre-generated token. If None, one will be generated.

        Returns:
            Session domain model with the raw token (returned once to client)
        """
        if token is None:
            token = self.generate_token()

        token_hash = self.hash_token(token)

        session = SessionDomain(
            id=secrets.token_hex(16),
            account_id=account_id,
            token_hash=token_hash,
            created_at=utc_now(),
            expires_at=utc_now() + timedelta(seconds=self._session_expiry),
            revoked_at=None,
            last_seen_at=None,
        )

        # Store the session (this stores only the hash, not the raw token)
        self._repo.create(session)

        return session

    def get_session_by_token(self, raw_token: str) -> SessionDomain | None:
        """Get a session by its raw token value.

        This hashes the provided token and looks up the session.

        Args:
            raw_token: The raw session token from the client

        Returns:
            Session domain model if found and active, None otherwise
        """
        token_hash = self.hash_token(raw_token)
        model = self._repo.get_active_by_token_hash(token_hash)

        if model:
            return SessionDomain(
                id=model.id,
                account_id=model.account_id,
                token_hash=model.token_hash,
                created_at=model.created_at,
                expires_at=model.expires_at,
                revoked_at=model.revoked_at,
                last_seen_at=model.last_seen_at,
            )
        return None

    def get_session_by_id(self, session_id: str) -> SessionDomain | None:
        """Get a session by its ID.

        Args:
            session_id: The session ID

        Returns:
            Session domain model if found, None otherwise
        """
        model = self._repo.get(session_id)
        if model:
            return SessionDomain(
                id=model.id,
                account_id=model.account_id,
                token_hash=model.token_hash,
                created_at=model.created_at,
                expires_at=model.expires_at,
                revoked_at=model.revoked_at,
                last_seen_at=model.last_seen_at,
            )
        return None

    def get_active_sessions_for_account(self, account_id: str) -> list[SessionDomain]:
        """Get all active sessions for an account.

        Args:
            account_id: The account ID

        Returns:
            List of active sessions for the account
        """
        models = self._repo.get_active_sessions_by_account(account_id)
        return [
            SessionDomain(
                id=m.id,
                account_id=m.account_id,
                token_hash=m.token_hash,
                created_at=m.created_at,
                expires_at=m.expires_at,
                revoked_at=m.revoked_at,
                last_seen_at=m.last_seen_at,
            )
            for m in models
        ]

    def revoke_session(self, session_id: str) -> bool:
        """Revoke a session.

        Args:
            session_id: The session ID to revoke

        Returns:
            True if session was found and revoked
        """
        return self._repo.revoke(session_id)

    def revoke_all_sessions_for_account(self, account_id: str) -> int:
        """Revoke all sessions for an account.

        Args:
            account_id: The account ID

        Returns:
            Number of sessions revoked
        """
        return self._repo.revoke_all_for_account(account_id)

    def update_last_seen(self, session_id: str) -> bool:
        """Update the last seen timestamp for a session.

        Args:
            session_id: The session ID

        Returns:
            True if session was found and updated
        """
        return self._repo.update_last_seen(session_id)

    def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions.

        Returns:
            Number of sessions removed
        """
        return self._repo.cleanup_expired()


@lru_cache()
def get_session_service() -> SessionService:
    """Get cached session service instance."""
    return SessionService()


def reset_session_service() -> None:
    """Reset the cached session service (useful for testing)."""
    get_session_service.cache_clear()
