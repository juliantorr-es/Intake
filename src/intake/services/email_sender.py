"""Email sender interfaces and local-dev implementation."""

import os
from abc import ABC, abstractmethod
from typing import Protocol

from intake.config import get_settings
from intake.domain.time import utc_now


class EmailSender(Protocol):
    """Protocol for sending emails."""

    def send_verification_email(self, email: str, code: str) -> None:
        """Send a verification code to an email address."""
        ...


class LocalDevEmailSender:
    """Local-dev email sender that writes emails to a file sink."""

    def __init__(self, sink_dir: str | None = None):
        settings = get_settings()
        self.sink_dir = sink_dir or os.path.join(settings.workspace_root, ".build", "intake", "emails")
        os.makedirs(self.sink_dir, exist_ok=True)

    def send_verification_email(self, email: str, code: str) -> None:
        """Record a verification email in the local sink."""
        timestamp = utc_now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{timestamp}_{email.replace('@', '_at_')}.txt"
        filepath = os.path.join(self.sink_dir, filename)

        content = f"""To: {email}
Subject: Intake Email Verification
Date: {utc_now().isoformat()}

Your Intake verification code is: {code}

This code will expire in 15 minutes.
"""
        with open(filepath, "w") as f:
            f.write(content)
        
        # Also log to stdout for easy dev access
        print(f"\n[LOCAL DEV EMAIL] Sent to {email}: Verification Code is {code}\n")


def get_email_sender() -> EmailSender:
    """Get the configured email sender."""
    # For now, always use LocalDevEmailSender
    return LocalDevEmailSender()
