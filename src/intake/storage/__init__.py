"""Storage layer for Intake."""

from intake.storage.db import get_session
from intake.storage.models import (
    AccountModel,
    EventModel,
    PasskeyChallengeModel,
    PasskeyCredentialModel,
    QuoteModel,
    SessionModel,
    UploadModel,
    EmailVerificationCodeModel,
)
from intake.storage.repositories import (
    AccountRepository,
    ChallengeRepository,
    EventRepository,
    PasskeyRepository,
    QuoteRepository,
    SessionRepository,
    EmailVerificationRepository,
)

__all__ = [
    "get_session",
    "AccountModel",
    "EventModel",
    "PasskeyChallengeModel",
    "PasskeyCredentialModel",
    "QuoteModel",
    "SessionModel",
    "UploadModel",
    "EmailVerificationCodeModel",
    "AccountRepository",
    "ChallengeRepository",
    "EventRepository",
    "PasskeyRepository",
    "QuoteRepository",
    "SessionRepository",
    "EmailVerificationRepository",
]
