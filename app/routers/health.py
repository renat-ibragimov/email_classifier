"""Liveness endpoint used by the reverse proxy and uptime checks."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health", summary="Health check")
async def get_health() -> dict[str, str]:
    """Report that the service is up."""
    return {"status": "ok"}
