"""Local Upload Receiver - separate from Local Console.

This module provides a loopback-only multipart upload receiver for Intake.
It is intentionally separate from the Local Console to maintain clear boundaries.
"""

from intake.local_console.receiver.api import router as receiver_router
from intake.local_console.receiver.models import (
    LocalUploadedFileRecord,
    LocalUploadReceipt,
    LocalUploadSession,
    ReceiverAvailabilityStatus,
    ReceiverHandshakeChallenge,
    ReceiverHandshakeResponse,
    ReceiverRegistration,
)
from intake.local_console.receiver.route_decision import UploadRouteDecisionService
from intake.local_console.receiver.service import LocalReceiverService
from intake.local_console.receiver.storage import LocalReceiverStorageService

__all__ = [
    # Models
    "ReceiverHandshakeChallenge",
    "ReceiverHandshakeResponse",
    "ReceiverRegistration",
    "ReceiverAvailabilityStatus",
    "LocalUploadSession",
    "LocalUploadReceipt",
    "LocalUploadedFileRecord",
    # Services
    "LocalReceiverStorageService",
    "LocalReceiverService",
    "UploadRouteDecisionService",
    # Router
    "receiver_router",
]
