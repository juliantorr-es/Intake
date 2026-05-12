#!/usr/bin/env bash
set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."

# Ensure .env exists for local development
if [ ! -f .env ]; then
    echo "ERROR: .env file not found. Copy .env.example to .env first."
    echo "  cp .env.example .env"
    exit 1
fi

# Ensure build directory exists
mkdir -p .build/intake

# Start the FastAPI dev server
exec uvicorn intake.app:app --reload --port 8000 --host 0.0.0.0
