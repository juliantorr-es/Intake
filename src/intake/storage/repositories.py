"""Repository layer for database operations."""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any
from contextlib import contextmanager

from sqlmodel import select, and_, or_, func, update

from intake.config import get_settings
from intake.domain.accounts import Account, Session as SessionDomain, EmailVerificationCode
from intake.domain.time import utc_now
from intake.domain.crypto import EncryptedPayload
from intake.domain.events import Event, EventAggregateType, EventType, EventActorType
from intake.domain.passkeys import (
    ChallengeAction,
    PasskeyChallenge,
    PasskeyChallengeStatus,
    PasskeyCredential,
)
from intake.domain.quotes import Quote, QuoteStatus, Upload, UploadStatus
from intake.storage.db import get_session, Session as DBSession
from intake.storage.models import (
    AccountModel,
    EventModel,
    PasskeyChallengeModel,
    PasskeyCredentialModel,
    QuoteModel,
    SessionModel,
    UploadModel,
    EmailVerificationCodeModel,
    RegisteredDeviceModel,
    TrackedActionModel,
    TrackedNonceModel,
)


# ========== Abstract Repositories ==========


class BaseRepository(ABC):
    """Base repository interface."""

    @abstractmethod
    def get(self, id: str) -> Any | None:
        """Get by ID."""
        pass

    @abstractmethod
    def get_all(self) -> list[Any]:
        """Get all."""
        pass

    @abstractmethod
    def create(self, obj: Any) -> Any:
        """Create."""
        pass

    @abstractmethod
    def update(self, obj: Any) -> Any:
        """Update."""
        pass

    @abstractmethod
    def delete(self, id: str) -> None:
        """Delete."""
        pass


# ========== Account Repository ==========


class AccountRepository:
    """Repository for account operations."""

    def __init__(self, session: DBSession | None = None):
        self._session = session

    @contextmanager
    def _get_session(self) -> Any:
        """Get a session, using provided one or creating new."""
        if self._session:
            yield self._session
        else:
            with get_session() as session:
                yield session

    def get(self, id: str) -> AccountModel | None:
        """Get account by ID."""
        with self._get_session() as session:
            statement = select(AccountModel).where(AccountModel.id == id)
            return session.exec(statement).first()

    def get_by_id(self, id: str) -> Account | None:
        """Get account by ID as domain model."""
        model = self.get(id)
        if model:
            return model.to_domain()
        return None

    def get_by_email_hash(self, email_hash: str) -> Account | None:
        """Get account by normalized email hash."""
        with self._get_session() as session:
            statement = select(AccountModel).where(AccountModel.normalized_email_hash == email_hash)
            model = session.exec(statement).first()
            if model:
                return model.to_domain()
            return None

    def create(self, account: Account) -> Account:
        """Create a new account."""
        with self._get_session() as session:
            model = AccountModel.from_domain(account)
            session.add(model)
            session.commit()
            session.refresh(model)
            return model.to_domain()

    def update(self, account: Account) -> Account:
        """Update an account."""
        import json
        with self._get_session() as session:
            model = session.get(AccountModel, account.id)
            if model:
                model.updated_at = account.updated_at
                model.email_verified_at = account.email_verified_at
                model.normalized_email_hash = account.normalized_email_hash
                if account.encrypted_email:
                    model.encrypted_email = json.dumps(account.encrypted_email.model_dump())
                else:
                    model.encrypted_email = None
                session.commit()
                session.refresh(model)
                return model.to_domain()
            return account


# ========== Challenge Repository ==========


class ChallengeRepository:
    """Repository for passkey challenge operations."""

    def __init__(self, session: DBSession | None = None):
        self._session = session

    @contextmanager
    def _get_session(self) -> Any:
        """Get a session, using provided one or creating new."""
        if self._session:
            yield self._session
        else:
            with get_session() as session:
                yield session

    def get(self, challenge_id: str) -> PasskeyChallengeModel | None:
        """Get challenge by ID."""
        with self._get_session() as session:
            statement = select(PasskeyChallengeModel).where(
                PasskeyChallengeModel.id == challenge_id
            )
            return session.exec(statement).first()

    def get_by_challenge_value(self, challenge: str) -> PasskeyChallengeModel | None:
        """Get challenge by challenge value (for verification)."""
        with self._get_session() as session:
            statement = select(PasskeyChallengeModel).where(
                PasskeyChallengeModel.challenge == challenge
            )
            return session.exec(statement).first()

    def get_pending_by_account(self, account_id: str) -> list[PasskeyChallengeModel]:
        """Get all pending challenges for an account."""
        with self._get_session() as session:
            statement = select(PasskeyChallengeModel).where(
                and_(
                    PasskeyChallengeModel.account_id == account_id,
                    PasskeyChallengeModel.status == PasskeyChallengeStatus.PENDING,
                    PasskeyChallengeModel.expires_at > utc_now(),
                )
            )
            return list(session.exec(statement).all())

    def create(self, challenge: PasskeyChallenge) -> PasskeyChallenge:
        """Create a new passkey challenge."""
        with self._get_session() as session:
            model = PasskeyChallengeModel(
                id=challenge.id,
                challenge=challenge.challenge,
                rp_id=challenge.rp_id,
                origin=challenge.origin,
                action=challenge.action,
                status=challenge.status,
                account_id=challenge.account_id,
                created_at=challenge.created_at,
                expires_at=challenge.expires_at,
                consumed_at=challenge.consumed_at,
                attempt_count=challenge.attempt_count,
            )
            session.add(model)
            session.commit()
            session.refresh(model)
            return challenge

    def mark_consumed(self, challenge_id: str) -> bool:
        """Mark a challenge as consumed."""
        with self._get_session() as session:
            model = session.get(PasskeyChallengeModel, challenge_id)
            if model and model.status == PasskeyChallengeStatus.PENDING:
                model.status = PasskeyChallengeStatus.CONSUMED
                model.consumed_at = utc_now()
                session.commit()
                return True
            return False

    def increment_attempt(self, challenge_id: str) -> bool:
        """Increment the attempt count for a challenge."""
        with self._get_session() as session:
            model = session.get(PasskeyChallengeModel, challenge_id)
            if model:
                model.attempt_count += 1
                session.commit()
                return True
            return False

    def invalidate_expired(self) -> int:
        """Mark all expired challenges as expired. Returns count."""
        with self._get_session() as session:
            statement = (
                update(PasskeyChallengeModel)
                .where(
                    and_(
                        PasskeyChallengeModel.status == PasskeyChallengeStatus.PENDING,
                        PasskeyChallengeModel.expires_at < utc_now(),
                    )
                )
                .values(status=PasskeyChallengeStatus.EXPIRED)
            )
            result = session.exec(statement)
            session.commit()
            return result.rowcount


# ========== Session Repository ==========


class SessionRepository:
    """Repository for session operations."""

    def __init__(self, session: DBSession | None = None):
        self._session = session

    @contextmanager
    def _get_session(self) -> Any:
        """Get a session, using provided one or creating new."""
        if self._session:
            yield self._session
        else:
            with get_session() as session:
                yield session

    def get(self, session_id: str) -> SessionModel | None:
        """Get session by ID."""
        with self._get_session() as session:
            statement = select(SessionModel).where(SessionModel.id == session_id)
            return session.exec(statement).first()

    def get_active_by_token_hash(self, token_hash: str) -> SessionModel | None:
        """Get active session by token hash."""
        with self._get_session() as session:
            statement = select(SessionModel).where(
                and_(
                    SessionModel.token_hash == token_hash,
                    SessionModel.revoked_at.is_(None),
                    SessionModel.expires_at > utc_now(),
                )
            )
            return session.exec(statement).first()

    def get_active_sessions_by_account(self, account_id: str) -> list[SessionModel]:
        """Get all active sessions for an account."""
        with self._get_session() as session:
            statement = select(SessionModel).where(
                and_(
                    SessionModel.account_id == account_id,
                    SessionModel.revoked_at.is_(None),
                    SessionModel.expires_at > utc_now(),
                )
            )
            return list(session.exec(statement).all())

    def create(self, session: SessionDomain) -> SessionDomain:
        """Create a new session."""
        with self._get_session() as session_db:
            # Check if there's already a session with this token hash
            existing = self.get_active_by_token_hash(session.token_hash)
            if existing:
                # This shouldn't happen if token generation is unique
                raise ValueError("Session with this token hash already exists")

            model = SessionModel(
                id=session.id,
                account_id=session.account_id,
                token_hash=session.token_hash,
                created_at=session.created_at,
                expires_at=session.expires_at,
                revoked_at=session.revoked_at,
                last_seen_at=session.last_seen_at,
            )
            session_db.add(model)
            session_db.commit()
            session_db.refresh(model)
            return session

    def revoke(self, session_id: str) -> bool:
        """Revoke a session."""
        with self._get_session() as session_db:
            model = session_db.get(SessionModel, session_id)
            if model and model.revoked_at is None:
                model.revoked_at = utc_now()
                session_db.commit()
                return True
            return False

    def revoke_all_for_account(self, account_id: str) -> int:
        """Revoke all sessions for an account. Returns count."""
        with self._get_session() as session_db:
            statement = (
                update(SessionModel)
                .where(
                    and_(
                        SessionModel.account_id == account_id,
                        SessionModel.revoked_at.is_(None),
                    )
                )
                .values(revoked_at=utc_now())
            )
            result = session_db.exec(statement)
            session_db.commit()
            return result.rowcount

    def update_last_seen(self, session_id: str) -> bool:
        """Update last seen timestamp for a session."""
        with self._get_session() as session_db:
            model = session_db.get(SessionModel, session_id)
            if model:
                model.last_seen_at = utc_now()
                session_db.commit()
                return True
            return False

    def cleanup_expired(self) -> int:
        """Remove expired sessions. Returns count removed."""
        with self._get_session() as session_db:
            statement = select(SessionModel).where(
                SessionModel.expires_at < utc_now()
            )
            models = list(session_db.exec(statement).all())
            for model in models:
                session_db.delete(model)
            session_db.commit()
            return len(models)


# ========== Passkey Repository ==========


class PasskeyRepository:
    """Repository for passkey operations."""

    def __init__(self, session: DBSession | None = None):
        self._session = session

    @contextmanager
    def _get_session(self) -> Any:
        """Get a session, using provided one or creating new."""
        if self._session:
            yield self._session
        else:
            with get_session() as session:
                yield session

    def get_credential(self, credential_id: str) -> PasskeyCredentialModel | None:
        """Get credential by credential_id."""
        with self._get_session() as session:
            statement = select(PasskeyCredentialModel).where(
                PasskeyCredentialModel.credential_id == credential_id
            )
            return session.exec(statement).first()

    def get_active_credentials_by_account(self, account_id: str) -> list[PasskeyCredentialModel]:
        """Get all active credentials for an account."""
        with self._get_session() as session:
            statement = select(PasskeyCredentialModel).where(
                and_(
                    PasskeyCredentialModel.account_id == account_id,
                    PasskeyCredentialModel.revoked_at.is_(None),
                )
            )
            return list(session.exec(statement).all())

    def create_credential(self, credential: PasskeyCredential) -> PasskeyCredential:
        """Create a new passkey credential."""
        with self._get_session() as session:
            model = PasskeyCredentialModel(
                id=credential.id,
                credential_id=credential.credential_id,
                public_key=credential.public_key,
                sign_count=credential.sign_count,
                credential_type=credential.credential_type,
                account_id=credential.account_id,
                registered_at=credential.registered_at,
                last_used_at=credential.last_used_at,
                name=credential.name,
                transports=credential.transports,
                backup_eligible=credential.backup_eligible,
                backup_state=credential.backup_state,
                device_label=credential.device_label,
                revoked_at=credential.revoked_at,
            )
            session.add(model)
            session.commit()
            session.refresh(model)
            return credential

    def update_after_login(
        self, 
        credential_id: str, 
        new_sign_count: int,
        backup_eligible: bool | None = None,
        backup_state: bool | None = None,
    ) -> bool:
        """Update credential after successful login (update sign count, timestamp, and backup info)."""
        with self._get_session() as session:
            statement = select(PasskeyCredentialModel).where(
                PasskeyCredentialModel.credential_id == credential_id
            )
            model = session.exec(statement).first()
            if model and model.revoked_at is None:
                model.sign_count = new_sign_count
                model.last_used_at = utc_now()
                if backup_eligible is not None:
                    model.backup_eligible = backup_eligible
                if backup_state is not None:
                    model.backup_state = backup_state
                session.commit()
                return True
            return False

    def revoke_credential(self, credential_id: str) -> bool:
        """Revoke a credential."""
        with self._get_session() as session:
            statement = select(PasskeyCredentialModel).where(
                PasskeyCredentialModel.credential_id == credential_id
            )
            model = session.exec(statement).first()
            if model:
                model.revoked_at = utc_now()
                session.commit()
                return True
            return False


# ========== Quote Repository ==========




class QuoteRepository:
    """Repository for quote operations."""

    def __init__(self, session: DBSession | None = None):
        self._session = session

    @contextmanager
    def _get_session(self) -> Any:
        """Get a session, using provided one or creating new."""
        if self._session:
            yield self._session
        else:
            with get_session() as session:
                yield session

    def _load_uploads(self, session: Any, quote_model: QuoteModel) -> list[Any]:
        """Load uploads for a quote model."""
        statement = select(UploadModel).where(UploadModel.quote_id == quote_model.id)
        upload_models = session.exec(statement).all()
        return [m.to_domain() for m in upload_models]

    def get_by_id(self, quote_id: str) -> Quote | None:
        """Get quote by ID (domain model)."""
        with self._get_session() as session:
            statement = select(QuoteModel).where(QuoteModel.id == quote_id)
            model = session.exec(statement).first()
            if model:
                domain = model.to_domain()
                domain.uploads = self._load_uploads(session, model)
                return domain
            return None

    def get(self, quote_id: str) -> QuoteModel | None:
        """Get quote by ID (storage model)."""
        with self._get_session() as session:
            statement = select(QuoteModel).where(QuoteModel.id == quote_id)
            return session.exec(statement).first()

    def get_by_account(self, account_id: str) -> list[Quote]:
        """Get all quotes for an account (domain models)."""
        with self._get_session() as session:
            statement = select(QuoteModel).where(QuoteModel.account_id == account_id)
            models = session.exec(statement).all()
            results = []
            for m in models:
                domain = m.to_domain()
                domain.uploads = self._load_uploads(session, m)
                results.append(domain)
            return results

    def get_by_status(self, status: QuoteStatus) -> list[Quote]:
        """Get all quotes with a specific status (domain models)."""
        with self._get_session() as session:
            statement = select(QuoteModel).where(QuoteModel.status == status)
            models = session.exec(statement).all()
            results = []
            for m in models:
                domain = m.to_domain()
                domain.uploads = self._load_uploads(session, m)
                results.append(domain)
            return results

    def create(self, quote: Quote) -> Quote:
        """Create a new quote."""
        with self._get_session() as session:
            model = QuoteModel.from_domain(quote)
            session.add(model)
            session.commit()
            session.refresh(model)
            return model.to_domain()

    def update(self, quote: Quote) -> Quote | None:
        """Update a quote."""
        import json

        with self._get_session() as session:
            model = session.get(QuoteModel, quote.id)
            if model:
                model.service_lane = quote.service_lane
                model.short_summary = quote.short_summary
                model.detailed_description = quote.detailed_description
                model.preferred_timeline = quote.preferred_timeline
                model.general_service_area = quote.general_service_area
                model.status = quote.status
                model.updated_at = quote.updated_at

                if quote.encrypted_exact_location:
                    model.encrypted_exact_location = json.dumps(
                        quote.encrypted_exact_location.model_dump()
                    )
                if quote.encrypted_access_notes:
                    model.encrypted_access_notes = json.dumps(
                        quote.encrypted_access_notes.model_dump()
                    )
                if quote.encrypted_questionnaire:
                    model.encrypted_questionnaire = json.dumps(
                        quote.encrypted_questionnaire.model_dump()
                    )

                session.commit()
                session.refresh(model)
                return model.to_domain()
            return None

    def update_status(self, quote_id: str, status: QuoteStatus) -> bool:
        """Update quote status."""
        with self._get_session() as session:
            model = session.get(QuoteModel, quote_id)
            if model:
                model.status = status
                model.updated_at = utc_now()
                session.commit()
                return True
            return False

    def get_all(self) -> list[Quote]:
        """Get all quotes."""
        with self._get_session() as session:
            statement = select(QuoteModel)
            models = list(session.exec(statement).all())
            results = []
            for m in models:
                domain = m.to_domain()
                domain.uploads = self._load_uploads(session, m)
                results.append(domain)
            return results

    def add_upload(self, upload: Any) -> None:
        """Add an upload record."""
        with self._get_session() as session:
            model = UploadModel.from_domain(upload)
            session.add(model)
            session.commit()


# ========== Event Repository ==========


class EventRepository:
    """Repository for event operations."""

    def __init__(self, session: DBSession | None = None):
        self._session = session

    @contextmanager
    def _get_session(self) -> Any:
        """Get a session, using provided one or creating new."""
        if self._session:
            yield self._session
        else:
            with get_session() as session:
                yield session

    def append(self, event: Event) -> Event:
        """Append an event to the event store."""
        with self._get_session() as session:
            model = EventModel.from_domain(event)
            session.add(model)
            session.commit()
            session.refresh(model)
            return model.to_domain()

    def get_for_aggregate(
        self, aggregate_type: EventAggregateType, aggregate_id: str
    ) -> list[Event]:
        """Get all events for an aggregate."""
        with self._get_session() as session:
            statement = select(EventModel).where(
                and_(
                    EventModel.aggregate_type == aggregate_type,
                    EventModel.aggregate_id == aggregate_id,
                )
            )
            models = list(session.exec(statement).all())
            return [m.to_domain() for m in models]

    def get_by_type(self, event_type: EventType) -> list[Event]:
        """Get all events of a specific type."""
        with self._get_session() as session:
            statement = select(EventModel).where(EventModel.event_type == event_type)
            models = list(session.exec(statement).all())
            return [m.to_domain() for m in models]

    def get_recent(self, limit: int = 100) -> list[Event]:
        """Get recent events."""
        with self._get_session() as session:
            statement = select(EventModel).order_by(EventModel.created_at.desc()).limit(limit)
            models = list(session.exec(statement).all())
            return [m.to_domain() for m in models]


# ========== Email Verification Repository ==========


class EmailVerificationRepository:
    """Repository for email verification operations."""

    def __init__(self, session: DBSession | None = None):
        self._session = session

    @contextmanager
    def _get_session(self) -> Any:
        """Get a session, using provided one or creating new."""
        if self._session:
            yield self._session
        else:
            with get_session() as session:
                yield session

    def get_by_id(self, code_id: str) -> EmailVerificationCode | None:
        """Get code by ID."""
        with self._get_session() as session:
            model = session.get(EmailVerificationCodeModel, code_id)
            if model:
                return model.to_domain()
            return None

    def get_active_by_email_hash(self, email_hash: str) -> list[EmailVerificationCode]:
        """Get all active (not consumed, not expired) codes for an email hash."""
        with self._get_session() as session:
            statement = select(EmailVerificationCodeModel).where(
                and_(
                    EmailVerificationCodeModel.email_hash == email_hash,
                    EmailVerificationCodeModel.consumed_at.is_(None),
                    EmailVerificationCodeModel.expires_at > utc_now(),
                )
            )
            models = list(session.exec(statement).all())
            return [m.to_domain() for m in models]

    def create(self, code: EmailVerificationCode) -> EmailVerificationCode:
        """Create a new verification code."""
        with self._get_session() as session:
            model = EmailVerificationCodeModel.from_domain(code)
            session.add(model)
            session.commit()
            session.refresh(model)
            return model.to_domain()

    def update(self, code: EmailVerificationCode) -> EmailVerificationCode | None:
        """Update a verification code (e.g., increment attempts)."""
        with self._get_session() as session:
            model = session.get(EmailVerificationCodeModel, code.id)
            if model:
                model.attempts = code.attempts
                model.consumed_at = code.consumed_at
                session.commit()
                session.refresh(model)
                return model.to_domain()
            return None

    def consume(self, code_id: str) -> bool:
        """Mark a code as consumed."""
        with self._get_session() as session:
            model = session.get(EmailVerificationCodeModel, code_id)
            if model and not model.consumed_at:
                model.consumed_at = utc_now()
                session.commit()
                return True
            return False

    def cleanup_expired(self) -> int:
        """Remove expired codes. Returns count removed."""
        with self._get_session() as session:
            statement = select(EmailVerificationCodeModel).where(
                EmailVerificationCodeModel.expires_at < utc_now()
            )
            models = list(session.exec(statement).all())
            for model in models:
                session.delete(model)
            session.commit()
            return len(models)


# ========== Sync Repository ==========


class SyncRepository:
    """Repository for synchronization and device operations."""

    def __init__(self, session: DBSession | None = None):
        self._session = session

    @contextmanager
    def _get_session(self) -> Any:
        """Get a session, using provided one or creating new."""
        if self._session:
            yield self._session
        else:
            with get_session() as session:
                yield session

    def get_device(self, device_id: str) -> RegisteredDeviceModel | None:
        """Get registered device by ID."""
        with self._get_session() as session:
            statement = select(RegisteredDeviceModel).where(
                RegisteredDeviceModel.device_id == device_id
            )
            return session.exec(statement).first()

    def create_device(self, device: Any) -> Any:
        """Register a new device."""
        with self._get_session() as session:
            model = RegisteredDeviceModel.from_domain(device)
            session.add(model)
            session.commit()
            session.refresh(model)
            return model.to_domain()

    def is_action_seen(self, action_id: str) -> bool:
        """Check if an action ID has already been processed."""
        with self._get_session() as session:
            statement = select(TrackedActionModel).where(
                TrackedActionModel.action_id == action_id
            )
            return session.exec(statement).first() is not None

    def is_nonce_seen(self, device_id: str, nonce: str) -> bool:
        """Check if a nonce has already been used by a device."""
        with self._get_session() as session:
            statement = select(TrackedNonceModel).where(
                and_(
                    TrackedNonceModel.device_id == device_id,
                    TrackedNonceModel.nonce == nonce
                )
            )
            return session.exec(statement).first() is not None

    def track_action(self, action_id: str, device_id: str, issued_at: datetime) -> None:
        """Track an action ID to prevent replay."""
        with self._get_session() as session:
            model = TrackedActionModel(
                action_id=action_id,
                device_id=device_id,
                issued_at=issued_at
            )
            session.add(model)
            session.commit()

    def track_nonce(self, device_id: str, nonce: str, issued_at: datetime) -> None:
        """Track a nonce to prevent replay."""
        with self._get_session() as session:
            model = TrackedNonceModel(
                device_id=device_id,
                nonce=nonce,
                issued_at=issued_at
            )
            session.add(model)
            session.commit()
