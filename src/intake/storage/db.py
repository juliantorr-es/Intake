"""Database session management."""

from contextlib import contextmanager
from functools import lru_cache
from typing import Generator, Any

from sqlmodel import SQLModel, Session, create_engine

from intake.config import get_settings

# Import all models to ensure they're registered with SQLModel's metadata
from intake.storage.models import (  # noqa: F401
    AccountModel,
    EventModel,
    PasskeyCredentialModel,
    QuoteModel,
    SessionModel,
    UploadModel,
    EmailVerificationCodeModel,
    RegisteredDeviceModel,
    TrackedActionModel,
    TrackedNonceModel,
)


@lru_cache()
def get_engine() -> Any:
    """Get the SQLAlchemy engine."""
    settings = get_settings()
    database_url = settings.get_database_url_for_sqlmodel()
    return create_engine(database_url, echo=settings.is_local)


def reset_engine() -> None:
    """Reset the engine cache (useful for testing)."""
    get_engine.cache_clear()


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Get a database session."""
    engine = get_engine()
    # expire_on_commit=False allows models to remain accessible after commit
    # This is useful for repositories that return models directly
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_all_tables() -> None:
    """Create all tables in the database."""
    engine = get_engine()
    SQLModel.metadata.create_all(engine)


def drop_all_tables() -> None:
    """Drop all tables from the database (useful for testing)."""
    engine = get_engine()
    SQLModel.metadata.drop_all(engine)
