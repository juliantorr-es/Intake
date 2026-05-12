"""Repository layer for database operations."""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any
from contextlib import contextmanager

from sqlmodel import select, and_, or_, func

from intake.config import get_settings
from intake.domain.accounts import Account
from intake.domain.crypto import EncryptedPayload
from intake.domain.events import Event, EventAggregateType, EventType, EventActorType
from intake.domain.passkeys import PasskeyChallenge, PasskeyCredential
from intake.domain.quotes import Quote, QuoteStatus, UploadDeclaration
from intake.storage.db import get_session, Session
from intake.storage.models import (
    AccountModel,
    EventModel,
    PasskeyCredentialModel,
    QuoteModel,
    SessionModel,
    UploadDeclarationModel,
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

    def __init__(self, session: Session | None = None):
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
            return Account(
                id=model.id,
                created_at=model.created_at,
                updated_at=model.updated_at,
            )
        return None

    def create(self, account: Account) -> Account:
        """Create a new account."""
        with self._get_session() as session:
            model = AccountModel(
                id=account.id,
                created_at=account.created_at,
                updated_at=account.updated_at,
            )
            session.add(model)
            session.commit()
            session.refresh(model)
            return account

    def update(self, account: Account) -> Account:
        """Update an account."""
        with self._get_session() as session:
            model = session.get(AccountModel, account.id)
            if model:
                model.updated_at = account.updated_at
                session.commit()
                session.refresh(model)
            return account


# ========== Passkey Repository ==========


class PasskeyRepository:
    """Repository for passkey operations."""

    def __init__(self, session: Session | None = None):
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
        """Get credential by credential_id (hashed for lookup)."""
        with self._get_session() as session:
            statement = select(PasskeyCredentialModel).where(
                PasskeyCredentialModel.credential_id == credential_id
            )
            return session.exec(statement).first()

    def get_credentials_by_account(self, account_id: str) -> list[PasskeyCredentialModel]:
        """Get all credentials for an account."""
        with self._get_session() as session:
            statement = select(PasskeyCredentialModel).where(
                PasskeyCredentialModel.account_id == account_id
            )
            return list(session.exec(statement).all())

    def create_credential(self, credential: PasskeyCredential) -> PasskeyCredential:
        """Create a new passkey credential."""
        with self._get_session() as session:
            model = PasskeyCredentialModel(
                id=credential.id,
                credential_id=credential.credential_id,
                public_key=credential.public_key,
                counter=credential.counter,
                credential_type=credential.credential_type,
                account_id=credential.account_id,
                registered_at=credential.registered_at,
                last_used_at=credential.last_used_at,
                name=credential.name,
            )
            session.add(model)
            session.commit()
            session.refresh(model)
            return credential

    def update_credential_counter(self, credential_id: str, new_counter: int) -> bool:
        """Update the counter for a credential (anti-replay)."""
        with self._get_session() as session:
            model = session.get(PasskeyCredentialModel, credential_id)
            if model:
                model.counter = new_counter
                model.last_used_at = datetime.utcnow()
                session.commit()
                return True
            return False


# ========== Quote Repository ==========


class QuoteRepository:
    """Repository for quote operations."""

    def __init__(self, session: Session | None = None):
        self._session = session

    @contextmanager
    def _get_session(self) -> Any:
        """Get a session, using provided one or creating new."""
        if self._session:
            yield self._session
        else:
            with get_session() as session:
                yield session

    def get(self, quote_id: str) -> QuoteModel | None:
        """Get quote by ID."""
        with self._get_session() as session:
            statement = select(QuoteModel).where(QuoteModel.id == quote_id)
            return session.exec(statement).first()

    def get_by_account(self, account_id: str) -> list[QuoteModel]:
        """Get all quotes for an account."""
        with self._get_session() as session:
            statement = select(QuoteModel).where(QuoteModel.account_id == account_id)
            return list(session.exec(statement).all())

    def get_by_status(self, status: QuoteStatus) -> list[QuoteModel]:
        """Get all quotes with a specific status."""
        with self._get_session() as session:
            statement = select(QuoteModel).where(QuoteModel.status == status)
            return list(session.exec(statement).all())

    def create(self, quote: Quote) -> Quote:
        """Create a new quote."""
        import json

        with self._get_session() as session:
            model = QuoteModel.from_domain(quote)
            session.add(model)
            session.commit()
            session.refresh(model)
            return model.to_domain()

    def update(self, quote: Quote) -> Quote | None:
        """Update a quote."""
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
                model.updated_at = datetime.utcnow()
                session.commit()
                return True
            return False

    def get_all(self) -> list[Quote]:
        """Get all quotes."""
        with self._get_session() as session:
            statement = select(QuoteModel)
            models = list(session.exec(statement).all())
            return [m.to_domain() for m in models]


# ========== Event Repository ==========


class EventRepository:
    """Repository for event operations."""

    def __init__(self, session: Session | None = None):
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
