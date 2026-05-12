"""Provider configuration redaction utilities.

These utilities ensure that provider configurations never expose
secrets, tokens, credentials, or local filesystem paths in public
APIs, logs, or UI responses.
"""

import re
from typing import Any, Optional


# Patterns for sensitive values that should be redacted
SECRET_PATTERNS = [
    # API keys and tokens
    r'(?:api[_-]?key|apikey|token|secret|password|credential|auth)[_-]?[=:]\s*[\"\']?([a-zA-Z0-9_\-\.]{20,})[\"\']?',
    # Bearer tokens
    r'Bearer\s+[a-zA-Z0-9_\-\.]+',
    # Private keys (PEM format)
    r'-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----',
    r'-----BEGIN\s+EC\s+PRIVATE\s+KEY-----',
    r'-----BEGIN\s+OPENSSH\s+PRIVATE\s+KEY-----',
    # Generic secret patterns
    r'(?:access[_-]?key[_-]?id|secret[_-]?access[_-]?key)[_:=]\s*[\"\']?[a-zA-Z0-9/+=]{20,}[\"\']?',
    # Connection strings with passwords
    r'(?:postgresql|mysql|mongodb|redis|amqp)://[^:]+:[^@]+@',
    # AWS/S3 credentials
    r'(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}',
]

# Compiled patterns for efficiency
_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in SECRET_PATTERNS]

# Known secret key names
SECRET_KEY_NAMES = frozenset({
    "api_key", "apikey", "api-key",
    "secret", "secret_key", "secret-key",
    "token", "access_token", "access-token", "refresh_token", "refresh-token",
    "password", "passwd", "pwd",
    "credential", "credentials",
    "auth", "authorization",
    "private_key", "private-key", "privatekey",
    "signing_key", "signing-key",
    "encryption_key", "encryption-key",
    "sync_token", "sync-token",
    "database_url", "database-url",
    "connection_string", "connection-string",
    "session_secret", "session-secret",
    "access_key_id", "access-key-id",
    "secret_access_key", "secret-access-key",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "GOOGLE_DRIVE_API_KEY",
    "TAILSCALE_AUTH_KEY",
    "CLOUDFLARE_API_TOKEN",
})

# Known local-only key prefixes/suffixes
LOCAL_ONLY_KEY_PATTERNS = frozenset({
    "INTAKE_LOCAL_",
    "LOCALiega",
    "PRIVATE_",
    "DEV_",
    "TEST_",
    "SECRET_",
})

REDACTED_PLACEHOLDER = "[REDACTED]"
FILE_PATH_PLACEHOLDER = "[FILE_PATH_REDACTED]"


def redact_secret_value(value: str, context: Optional[str] = None) -> str:
    """Redact a value that might contain secrets.
    
    Args:
        value: The value to redact
        context: Optional context (e.g., key name) for more targeted redaction
        
    Returns:
        The redacted value safe for display
    """
    if not isinstance(value, str):
        # Non-string values (None, int, etc.) get redacted if context indicates secret
        if context and any(secret_name in context.lower() for secret_name in SECRET_KEY_NAMES):
            return REDACTED_PLACEHOLDER
        return REDACTED_PLACEHOLDER if value is None else str(value)
    
    if not value:
        # Empty string - okay to return as-is
        return value
    
    # If context indicates this is a secret key, redact entirely
    if context and any(secret_name in context.lower() for secret_name in SECRET_KEY_NAMES):
        return REDACTED_PLACEHOLDER
    
    # Check if value matches secret patterns
    for pattern in _COMPILED_PATTERNS:
        if pattern.search(value):
            return REDACTED_PLACEHOLDER
    
    # If value looks like a high-entropy secret (long alphanumeric)
    if len(value) > 32 and re.match(r'^[a-zA-Z0-9_\-\.=/+]+$', value):
        return REDACTED_PLACEHOLDER
    
    return value


def redact_dict_keys(dict_data: dict[str, Any], recursive: bool = True) -> dict[str, Any]:
    """Redact sensitive keys from a dictionary.
    
    Keys matching SECRET_KEY_NAMES or containing LOCAL_ONLY_KEY_PATTERNS
    will have their values replaced with REDACTED_PLACEHOLDER.
    
    Args:
        dict_data: The dictionary to redact
        recursive: Whether to recursively process nested dictionaries
        
    Returns:
        A new dictionary with sensitive values redacted
    """
    result = {}
    for key, value in dict_data.items():
        key_lower = key.lower()
        
        # Check if this key is sensitive
        is_secret_key = (
            any(secret_name in key_lower for secret_name in SECRET_KEY_NAMES) or
            any(pattern in key for pattern in LOCAL_ONLY_KEY_PATTERNS)
        )
        
        if is_secret_key:
            result[key] = REDACTED_PLACEHOLDER
        elif isinstance(value, dict) and recursive:
            result[key] = redact_dict_keys(value, recursive=True)
        elif isinstance(value, list) and recursive:
            result[key] = [
                redact_dict_keys(item, recursive=True) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[key] = redact_secret_value(value, context=key)
    
    return result


def redact_file_paths(value: Any) -> Any:
    """Redact filesystem paths from values.
    
    Args:
        value: The value to process
        
    Returns:
        The value with filesystem paths redacted
    """
    if isinstance(value, str):
        # Common path patterns
        path_patterns = [
            r'/home/[^/]+/',
            r'/Users/[^/]+/',
            r'C:\\Users\\[^\\]+\\',
            r'\.ssh/',
            r'\.config/',
            r'\.railway/',
            r'/tmp/',
            r'/var/',
            r'/etc/',
        ]
        
        for pattern in path_patterns:
            if re.search(pattern, value, re.IGNORECASE):
                return FILE_PATH_PLACEHOLDER
        
        # Also check for absolute paths
        if value.startswith('/') or value.startswith('C:\\') or '\\' in value:
            # More careful check - only redact if it looks like a real path
            if re.search(r'(?:/|\\)[a-zA-Z0-9_\-\./\\]+', value):
                return FILE_PATH_PLACEHOLDER
    
    elif isinstance(value, dict):
        return {k: redact_file_paths(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [redact_file_paths(item) for item in value]
    
    return value


def sanitize_provider_config(config: dict[str, Any]) -> dict[str, Any]:
    """Fully sanitize a provider configuration for safe display.
    
    This:
    1. Redacts all secret/credential values
    2. Redacts filesystem paths
    3. Preserves non-sensitive metadata
    
    Args:
        config: The provider configuration dictionary
        
    Returns:
        A sanitized copy safe for logs/APIs/UI
    """
    # First pass: redact by key
    sanitized = redact_dict_keys(config, recursive=True)
    
    # Second pass: redact file paths
    sanitized = redact_file_paths(sanitized)
    
    # Third pass: check string values for remaining secrets
    def check_value(v: Any) -> Any:
        if isinstance(v, str):
            # If it still looks sensitive after previous passes
            for pattern in _COMPILED_PATTERNS:
                if pattern.search(v):
                    return REDACTED_PLACEHOLDER
            if len(v) > 40 and re.match(r'^[a-zA-Z0-9_\-\.=/+]+$', v):
                return REDACTED_PLACEHOLDER
            return v
        elif isinstance(v, dict):
            return {k: check_value(val) for k, val in v.items()}
        elif isinstance(v, list):
            return [check_value(item) for item in v]
        return v
    
    return check_value(sanitized)


def get_redacted_fields(config: dict[str, Any]) -> list[str]:
    """Get list of field names that were redacted.
    
    Args:
        config: The original configuration
        
    Returns:
        List of field paths that were redacted (e.g., ["api_key", "database.password"])
    """
    redacted = []
    
    def _check_dict(d: dict[str, Any], prefix: str = "") -> None:
        for key, value in d.items():
            full_key = f"{prefix}.{key}" if prefix else key
            key_lower = key.lower()
            
            is_secret = (
                any(secret_name in key_lower for secret_name in SECRET_KEY_NAMES) or
                any(pattern in key for pattern in LOCAL_ONLY_KEY_PATTERNS)
            )
            
            if is_secret:
                redacted.append(full_key)
            elif isinstance(value, dict):
                _check_dict(value, full_key)
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        _check_dict(item, f"{full_key}[{i}]")
    
    _check_dict(config)
    return redacted
