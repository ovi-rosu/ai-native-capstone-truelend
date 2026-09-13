"""Platform-level routes: health probe only (see this story's scope_out)."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def get_health() -> dict[str, str]:
    """Trivial liveness probe -- no I/O, well under the read-latency budget."""
    return {"status": "ok"}
