"""SSE stream tests."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import app.api.analyses as analyses_api
import app.db.session as db_session
import pytest
from app.core.config import Settings
from app.db.base import Base
from app.db.models import Analysis, AnalysisEvent, AnalysisStatus, Deck
from app.db.session import get_db_session
from app.main import create_app
from app.repositories.events import EventRepository
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


@pytest.fixture
async def sse_client(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[tuple[AsyncClient, async_sessionmaker], None]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    monkeypatch.setattr(db_session, "_engine", engine)
    monkeypatch.setattr(db_session, "_session_factory", factory)
    monkeypatch.setattr(analyses_api, "get_session_factory", lambda: factory)

    settings = Settings(
        sse_heartbeat_seconds=0.05,
        sse_poll_interval_seconds=0.01,
        database_url="sqlite+aiosqlite://",
    )
    monkeypatch.setattr(analyses_api, "get_settings", lambda: settings)

    app = create_app()

    async def override_db() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, factory
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_sse_unknown_analysis(sse_client: tuple[AsyncClient, async_sessionmaker]) -> None:
    client, _ = sse_client
    response = await client.get(f"/api/v1/analyses/{uuid.uuid4()}/events")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_sse_replays_and_terminates(
    sse_client: tuple[AsyncClient, async_sessionmaker],
) -> None:
    client, factory = sse_client

    async with factory() as session:
        deck = Deck(name="D", format="modern", cards=[{"name": "Mountain", "quantity": 1}])
        session.add(deck)
        await session.flush()
        analysis = Analysis(
            deck_id=deck.id,
            status=AnalysisStatus.COMPLETED.value,
            options={"budget_usd": 10, "recommendation_count": 1},
            metrics={"total_cards": 1},
            result={"summary": "done", "recommendations": [], "warnings": []},
        )
        session.add(analysis)
        await session.flush()
        events = EventRepository(session)
        await events.append(
            analysis_id=analysis.id, event_type="queued", payload={"status": "queued"}
        )
        await events.append(
            analysis_id=analysis.id,
            event_type="progress",
            payload={"step": "fetch_cards", "percent": 20},
        )
        await events.append(
            analysis_id=analysis.id,
            event_type="completed",
            payload={"analysis_id": str(analysis.id), "status": "completed"},
        )
        await session.commit()
        analysis_id = analysis.id

    async with client.stream("GET", f"/api/v1/analyses/{analysis_id}/events") as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        body = ""
        async for chunk in response.aiter_text():
            body += chunk
            if "event: completed" in body:
                break

    assert "id: 1" in body
    assert "event: queued" in body
    assert "event: progress" in body
    assert "event: completed" in body


@pytest.mark.asyncio
async def test_sse_last_event_id_replay(
    sse_client: tuple[AsyncClient, async_sessionmaker],
) -> None:
    client, factory = sse_client

    async with factory() as session:
        deck = Deck(name="D", format="modern", cards=[{"name": "Mountain", "quantity": 1}])
        session.add(deck)
        await session.flush()
        analysis = Analysis(
            deck_id=deck.id,
            status=AnalysisStatus.COMPLETED.value,
            options={},
        )
        session.add(analysis)
        await session.flush()
        session.add_all(
            [
                AnalysisEvent(
                    analysis_id=analysis.id, event_type="queued", payload={"status": "queued"}
                ),
                AnalysisEvent(
                    analysis_id=analysis.id,
                    event_type="completed",
                    payload={"status": "completed"},
                ),
            ]
        )
        await session.commit()
        analysis_id = analysis.id

    async with client.stream(
        "GET",
        f"/api/v1/analyses/{analysis_id}/events",
        headers={"Last-Event-ID": "1"},
    ) as response:
        body = ""
        async for chunk in response.aiter_text():
            body += chunk
            if "event: completed" in body:
                break

    assert "event: queued" not in body
    assert "event: completed" in body
