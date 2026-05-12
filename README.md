# Intake

Passkey-gated, locally decryptable client intake platform for a freelance services website.

## Architecture

Intake follows a clear separation between the **public backend** and the **local operator console**:

- **Public Backend**: receives, validates, encrypts, stores, and notifies
- **Local Operator Console**: decrypts, reviews, quotes, schedules, and acts

### Core Boundaries

- No passwords - passkey-first authentication only
- No raw session tokens in storage
- No plaintext sensitive data in long-term database
- Encryption for readable sensitive data
- Hashing only for lookup/deduplication
- No innerHTML for user-controlled frontend content
- No eval or dynamic code execution
- No subprocess or Git commands from public backend

## Setup

```bash
# Clone and enter repo
cd Intake

# Create virtual environment (optional but recommended)
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Copy environment file
cp .env.example .env

# Edit .env and set INTAKE_DEV_ENCRYPTION_KEY
# Generate with: openssl rand -base64 32

# Initialize database
mkdir -p .build/intake
touch .build/intake/local.db

# Create initial migrations (if needed)
alembic revision --autogenerate -m "initial" 2>/dev/null || true
alembic upgrade head 2>/dev/null || true
```

## Development

```bash
# Start the dev server
./scripts/dev.sh

# Or directly:
uvicorn intake.app:app --reload --port 8000

# Open http://localhost:8000
```

## Tests

```bash
# Run all checks
./scripts/check.sh

# Or individually:
ruff check .
ruff format .
pytest
```

## Project Structure

```
Intake/
├── src/intake/
│   ├── app.py              # FastAPI application entry
│   ├── config.py           # Configuration management
│   ├── api/
│   │   ├── __init__.py
│   │   ├── health.py       # Health check endpoint
│   │   ├── auth_passkeys.py # Passkey authentication endpoints
│   │   └── quotes.py       # Quote intake endpoints
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── accounts.py     # Account domain models
│   │   ├── passkeys.py     # Passkey domain models
│   │   ├── quotes.py       # Quote domain models
│   │   ├── crypto.py       # Encryption primitives domain
│   │   ├── events.py       # Event sourcing models
│   │   └── projections.py  # Projection models for UI
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── db.py           # Database session management
│   │   ├── models.py       # SQLModel persistence models
│   │   └── repositories.py # Repository layer
│   ├── services/
│   │   ├── __init__.py
│   │   ├── passkey_service.py
│   │   ├── quote_service.py
│   │   ├── crypto_service.py
│   │   └── event_log.py
│   └── operator_console/
│       ├── __init__.py
│       ├── cli.py         # CLI entry point
│       └── decrypt.py     # Decryption utilities
├── tests/
│   ├── test_health.py
│   ├── test_crypto_service.py
│   ├── test_quote_models.py
│   ├── test_event_log.py
│   └── test_passkey_shapes.py
├── scripts/
│   ├── dev.sh              # Start dev server
│   └── check.sh            # Run linting and tests
└── web/
    └── static/
        ├── css/
        └── js/
    └── templates/
```

## Security Notes

### Encryption vs Hashing

- **Hashing** is used for lookup/deduplication only (challenges, credential IDs)
- **Encryption** is used for data that needs to be read later (quote payloads, exact locations)

### Production Key Management

Production key management is **intentionally not solved** in this bootstrap. The intended future architecture:

- Local private-key decryption for sensitive quote payloads
- Operator console unlocks with local private key
- No private keys in the public backend

### Current Limitations

This bootstrap uses a single development encryption key from the environment. In production:

- Use proper key management (HSM, KMS, or secure key vault)
- Implement key rotation
- Separate encryption keys per tenant/data type
- Never store private keys in the backend database

## Service Lanes

Quote intake supports these service lanes:

- `software_systems` - Custom software development
- `photography` - Photography services
- `practical_help` - Hands-on assistance
- `unsure` - Unsure of needs

## Quote Status Flow

```
draft -> submitted -> needs_review -> reviewing -> quoted -> accepted -> closed
                                   -> quoted -> declined -> closed
```
