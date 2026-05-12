"""Local Console API routers."""

from fastapi import APIRouter

from intake.local_console.api.main import router as main_router, get_local_review_service
from intake.local_console.api.costs import router as costs_router
from intake.local_console.api.proof_rail import router as proof_rail_router
from intake.local_console.api.security import router as security_router

# Combine all Local Console API routers
router = APIRouter()
router.include_router(main_router)
router.include_router(costs_router, tags=["costs"])
router.include_router(proof_rail_router, prefix="/proof-rail", tags=["proof-rail"])
router.include_router(security_router)

__all__ = ["router", "get_local_review_service"]
