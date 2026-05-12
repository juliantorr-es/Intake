"""Decryption utilities for operator console."""

import json
from typing import Any

from intake.config import get_settings
from intake.domain.crypto import EncryptedPayload
from intake.services.crypto_service import get_crypto_service
from intake.storage.repositories import QuoteRepository


def decrypt_quote_payload(
    encrypted_payload: str | EncryptedPayload | None,
) -> dict[str, Any] | None:
    """Decrypt a single encrypted payload.

    Args:
        encrypted_payload: Encrypted payload (as JSON string, dict, or EncryptedPayload)

    Returns:
        Decrypted dictionary or None if no payload
    """
    if encrypted_payload is None:
        return None

    crypto = get_crypto_service()

    # Parse if it's a JSON string
    if isinstance(encrypted_payload, str):
        try:
            encrypted_payload = json.loads(encrypted_payload)
        except json.JSONDecodeError:
            pass

    # Convert dict to EncryptedPayload
    if isinstance(encrypted_payload, dict):
        encrypted_payload = EncryptedPayload(**encrypted_payload)

    if not isinstance(encrypted_payload, EncryptedPayload):
        return None

    return crypto.decrypt_json(encrypted_payload)


def decrypt_quote_full(quote_id: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Get and decrypt all fields of a quote.

    Returns a tuple of (safe_data, sensitive_data) where:
    - safe_data: Non-sensitive data that can be displayed without decryption
    - sensitive_data: Decrypted sensitive data

    Args:
        quote_id: ID of the quote to decrypt

    Returns:
        Tuple of (safe_data, sensitive_data) or None if quote not found
    """
    repo = QuoteRepository()
    model = repo.get(quote_id)

    if not model:
        return None

    domain_quote = model.to_domain()

    # Safe data (already visible)
    safe_data = domain_quote.get_safe_summary()

    # Decrypt sensitive data
    sensitive_data: dict[str, Any] = {}

    if domain_quote.encrypted_exact_location:
        decrypted = decrypt_quote_payload(domain_quote.encrypted_exact_location)
        if decrypted:
            sensitive_data["exact_location"] = decrypted.get("location")

    if domain_quote.encrypted_access_notes:
        decrypted = decrypt_quote_payload(domain_quote.encrypted_access_notes)
        if decrypted:
            sensitive_data["access_notes"] = decrypted.get("notes")

    if domain_quote.encrypted_questionnaire:
        decrypted = decrypt_quote_payload(domain_quote.encrypted_questionnaire)
        if decrypted:
            sensitive_data["questionnaire"] = decrypted

    # Add upload info
    if domain_quote.upload_declarations:
        sensitive_data["uploads"] = [
            {
                "upload_id": u.upload_id,
                "original_filename": u.original_filename,
                "content_type": u.content_type,
                "size_bytes": u.size_bytes,
                "purpose": u.purpose,
            }
            for u in domain_quote.upload_declarations
        ]

    return safe_data, sensitive_data
