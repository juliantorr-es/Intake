# AGENTS.md - Intake Project

Conventions for AI agents and humans contributing to **Intake** — a passkey-gated client intake platform.

## Git Discipline

- Never use `git commit --amend`, `git push --force`, or `git push --force-with-lease`
- Always create new commits and push with a plain `git push`
- If a push is rejected due to upstream changes, rebase onto the updated remote branch — never merge and never force-push

## Project Layout

- `src/intake/` - Main application code with explicit `src/` layout
- `__init__.py` exposes public API via explicit `__all__`
- Domain models in `domain/` - pure Python, no framework dependencies
- Storage models in `storage/` - SQLModel models and repositories
- API endpoints in `api/` - FastAPI route handlers
- Services in `services/` - business logic coordination
- Operator console in `operator_console/` - local CLI tools

## Commands

```bash
# Run dev server
./scripts/dev.sh

# Run all checks (lint, format, test)
./scripts/check.sh

# Individual commands
ruff check .
ruff format .
pytest
```

## Python Style

- Python >= 3.10 required, 3.12+ preferred
- Modern type hints: built-in generics (`list`, `dict`) and `|` unions
- Use `pathlib.Path` instead of `os.path`
- Follow PEP 8, prefer f-strings and comprehensions
- Early returns and guard clauses over nested blocks
- No relative imports - always absolute from package root

## Security Posture

- **Never** use `innerHTML` for user-controlled content - use `textContent`
- **Never** use `eval`, `exec`, or dynamic code execution
- **Never** browse filesystem from public routes
- **Never** run Git commands or subprocess from public backend
- Use encryption for sensitive data, hashing only for lookup
- No passwords - passkey-first authentication only
- No raw session tokens in storage
- No raw verification secrets in storage

## Testing

- Stack: `pytest` + `pytest-asyncio` + `httpx`
- Tests live in `tests/` mirroring source layout
- No docstrings on test functions - use descriptive names
- Add `TODO` markers only where external integration is required

## Dependencies

- FastAPI for public backend
- Uvicorn for development
- Pydantic for request/response/domain models
- SQLModel for persistence models
- Alembic for migrations
- pytest for tests
- ruff for lint/format
- py-webauthn for WebAuthn/passkey server-side verification
- cryptography for encryption primitives
- python-dotenv for local configuration

## Architecture Boundaries

- Public API must be small and explicit
- No arbitrary widget kinds
- No payment processing in this slice
- No Google Calendar integration in this slice
- No external email provider in this slice
- No real object storage in this slice
- No custom cryptography - use established library primitives only
