#!/usr/bin/env bash
set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."

# Ensure .env exists for local development
if [ ! -f .env ]; then
    echo "WARNING: .env file not found. Copy .env.example to .env for full checks."
    echo "  cp .env.example .env"
fi

echo "==> Running ruff check..."
ruff check .

echo "==> Running ruff format check..."
ruff format --check .

echo "==> Running pytest..."
pytest

echo "==> All checks passed!"
