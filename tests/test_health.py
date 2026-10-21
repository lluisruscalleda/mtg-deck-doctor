"""Health endpoint tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from app.main import create_app
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_health_ok() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_ready_reports_degraded_without_services() -> None:
    app = create_app()
    transport = ASGITransport(app=app)

    with (
        patch("app.api.health.get_engine", side_effect=RuntimeError("no db")),
        patch(
            "app.api.health.check_rabbitmq_connectivity",
            new=AsyncMock(side_effect=RuntimeError("no mq")),
        ),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["database"] == "unavailable"
    assert body["checks"]["rabbitmq"] == "unavailable"
    assert "postgresql" not in response.text.lower()
    assert "amqp://" not in response.text
