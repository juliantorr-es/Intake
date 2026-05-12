"""FastAPI application for Intake."""

import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Ensure src is in path for relative imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from intake.api import api_router
from intake.config import get_settings
from intake.storage.db import create_all_tables


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    # Startup: ensure tables exist
    settings = get_settings()
    build_path = settings.ensure_build_dir()

    # Ensure database directory exists
    db_path = Path(".build/intake")
    db_path.mkdir(parents=True, exist_ok=True)

    # Create tables
    create_all_tables()

    yield

    # Shutdown


# Create the FastAPI app
app = FastAPI(
    title="Intake",
    description="Passkey-gated, locally decryptable client intake platform",
    version="0.1.0",
    lifespan=lifespan,
)

# Include API routes
app.include_router(api_router, prefix="/api")

# Set up static files and templates
static_dir = Path(__file__).parent / "web" / "static"
templates_dir = Path(__file__).parent / "web" / "templates"

if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

if templates_dir.exists():
    templates = Jinja2Templates(directory=str(templates_dir))


# ========== HTML Endpoints for Local Dev ==========


@app.get("/")
async def index(request: Request) -> Any:
    """Landing page."""
    from fastapi.responses import HTMLResponse

    settings = get_settings()
    context = {
        "request": request,
        "base_url": settings.intake_base_url,
        "title": "Intake - Freelance Services",
    }
    return templates.TemplateResponse("index.html", context)


@app.get("/quote")
async def quote_page(request: Request) -> Any:
    """Quote intake demo page."""
    from fastapi.responses import HTMLResponse

    settings = get_settings()
    context = {
        "request": request,
        "base_url": settings.intake_base_url,
        "title": "Request a Quote - Intake",
    }
    return templates.TemplateResponse("quote.html", context)


@app.get("/account")
async def account_page(request: Request) -> Any:
    """Account/passkey demo page."""
    from fastapi.responses import HTMLResponse

    settings = get_settings()
    context = {
        "request": request,
        "base_url": settings.intake_base_url,
        "title": "Account - Intake",
        "rp_name": settings.intake_rp_name,
        "rp_id": settings.intake_rp_id,
        "origin": settings.intake_origin,
    }
    return templates.TemplateResponse("account.html", context)
