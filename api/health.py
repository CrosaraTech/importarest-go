"""GET /health endpoint — simple liveness check, no external dependencies."""
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict:
    """Returns {"status": "ok"} if the server is running.

    Does NOT access G: drive, Supabase, Redis, or any external system.
    Useful for load-balancer health checks and smoke tests.
    """
    return {"status": "ok"}
