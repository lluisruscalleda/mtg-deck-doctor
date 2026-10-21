"""Health and readiness endpoints."""

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import get_engine
from app.messaging.rabbitmq import check_rabbitmq_connectivity

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness() -> dict[str, object]:
    settings = get_settings()
    checks: dict[str, str] = {}
    overall = "ok"

    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "unavailable"
        overall = "degraded"

    try:
        await check_rabbitmq_connectivity(settings.rabbitmq_url)
        checks["rabbitmq"] = "ok"
    except Exception:
        checks["rabbitmq"] = "unavailable"
        overall = "degraded"

    return {"status": overall, "checks": checks}
