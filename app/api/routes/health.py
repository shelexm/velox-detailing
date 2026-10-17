"""Liveness and readiness probes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health/live")
async def live() -> dict[str, str]:
    """The process is up and serving requests."""
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(request: Request) -> JSONResponse:
    """The database answers and its schema is at the migration head this code expects."""
    checks: dict[str, str] = {}
    try:
        async with request.app.state.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            checks["database"] = "ok"
            current = (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalars().all()
        expected = request.app.state.migration_heads
        checks["migrations"] = "ok" if set(current) == set(expected) else "pending"
    except Exception:
        logger.warning("Readiness check failed", exc_info=True)
        checks.setdefault("database", "unavailable")
        checks.setdefault("migrations", "unknown")
    healthy = all(value == "ok" for value in checks.values())
    return JSONResponse(
        {"status": "ok" if healthy else "unavailable", "checks": checks}, status_code=200 if healthy else 503
    )
