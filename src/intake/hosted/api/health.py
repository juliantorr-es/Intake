"""Health check endpoint."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str
    version: str = "0.1.0"


class ReadinessResponse(BaseModel):
    """Readiness check response model."""

    ready: bool = True
    database: bool = True


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="ok")


@router.get("/ready", response_model=ReadinessResponse)
async def readiness_check() -> ReadinessResponse:
    """Readiness check endpoint."""
    # In a real implementation, we'd check database connectivity
    return ReadinessResponse(ready=True, database=True)
