"""Local Console API routers."""

from fastapi import APIRouter

from intake.local_console.api.costs import router as costs_router
from intake.local_console.api.main import router as main_router, get_local_review_service

# Combine all Local Console API routers
router = APIRouter()
router.include_router(main_router)
router.include_router(costs_router, prefix="/costs", tags=["costs"])

__all__ = ["router", "get_local_review_service"]
