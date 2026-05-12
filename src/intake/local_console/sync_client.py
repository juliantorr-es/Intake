"""Local sync client for pulling data from hosted backend."""


import httpx

from intake.config import get_settings
from intake.sync.models import (
    EncryptedQuoteEnvelope,
    HostedQuoteProjection,
    LocalDeviceActionEnvelope,
)


class LocalSyncClient:
    """Outbound client for Local Console to pull data from Hosted Intake."""

    def __init__(self, base_url: str | None = None, sync_token: str | None = None):
        """Initialize sync client.
        
        Args:
            base_url: Hosted backend base URL
            sync_token: Temporary local-dev sync token
        """
        settings = get_settings()
        self.base_url = base_url or settings.intake_base_url

        if sync_token:
            self.sync_token = sync_token
        elif settings.intake_local_sync_token:
            self.sync_token = settings.intake_local_sync_token.get_secret_value()
        else:
            self.sync_token = ""

    def _get_headers(self) -> dict[str, str]:
        """Get required headers for sync auth."""
        return {
            "X-Intake-Sync-Token": self.sync_token,
            "Accept": "application/json",
        }

    def fetch_pending_projections(self) -> list[HostedQuoteProjection]:
        """Fetch redacted quote projections from hosted backend."""
        url = f"{self.base_url}/api/sync/quotes/pending"

        with httpx.Client(timeout=10.0) as client:
            response = client.get(url, headers=self._get_headers())

            if response.status_code == 401:
                raise PermissionError("Missing or invalid sync token")
            elif response.status_code != 200:
                raise RuntimeError(f"Failed to fetch projections: {response.status_code} - {response.text}")

            data = response.json()
            return [HostedQuoteProjection(**item) for item in data]

    def fetch_quote_envelope(self, quote_id: str) -> EncryptedQuoteEnvelope:
        """Fetch encrypted envelope for a specific quote."""
        url = f"{self.base_url}/api/sync/quotes/{quote_id}/envelope"

        with httpx.Client(timeout=10.0) as client:
            response = client.get(url, headers=self._get_headers())

            if response.status_code == 404:
                raise ValueError(f"Quote {quote_id} not found on hosted backend")
            elif response.status_code != 200:
                raise RuntimeError(f"Failed to fetch envelope: {response.status_code} - {response.text}")

            data = response.json()
            return EncryptedQuoteEnvelope(**data)

    def push_action(self, envelope: LocalDeviceActionEnvelope) -> dict:
        """Push a signed action to the hosted backend."""
        url = f"{self.base_url}/api/sync/actions"

        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                url,
                headers=self._get_headers(),
                content=envelope.model_dump_json()
            )

            if response.status_code == 403:
                raise PermissionError(f"Action rejected by hosted backend: {response.text}")
            elif response.status_code != 200:
                raise RuntimeError(f"Failed to push action: {response.status_code} - {response.text}")

            return response.json()
