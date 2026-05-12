"""API endpoints for Intake."""

from intake.api.health import router as health_router
from intake.api.auth_passkeys import router as auth_router
from intake.api.quotes import router as quotes_router
from intake.api.account import router as account_router

# Combine all routers
from fastapi import APIRouter

api_router = APIRouter()
api_router.include_router(health_router, prefix="")
api_router.include_router(auth_router, prefix="/auth")
api_router.include_router(quotes_router, prefix="/quotes")
api_router.include_router(account_router, prefix="/account")
