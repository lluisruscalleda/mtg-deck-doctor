"""Analysis API tests."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
from app.api.deps import get_scryfall_client
from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.services.scryfall import ScryfallClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from tests.fakes import FakeScryfall, make_card


@pytest.fixture
async def api_client() -> AsyncGenerator[AsyncClient, None]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    app = create_app()
    fake = FakeScryfall(
        {
            "Lightning Bolt": make_card("Lightning Bolt"),
            "Mountain": make_card(
                "Mountain", type_line="Basic Land — Mountain", colors=[], cmc=0
            ),
        }
    )

    async def override_db() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            yield session

    async def override_scryfall() -> AsyncGenerator[ScryfallClient, None]:
        yield fake

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_scryfall_client] = override_scryfall

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_and_get_analysis(api_client: AsyncClient) -> None:
    deck = await api_client.post(
        "/api/v1/decks",
        json={
            "name": "Burn",
            "format": "modern",
            "cards": [
                {"name": "Lightning Bolt", "quantity": 4},
                {"name": "Mountain", "quantity": 20},
            ],
        },
    )
    assert deck.status_code == 201
    deck_id = deck.json()["id"]

    created = await api_client.post(
        f"/api/v1/decks/{deck_id}/analyses",
        json={"budget_usd": 25, "recommendation_count": 2},
    )
    assert created.status_code == 202
    body = created.json()
    assert body["status"] == "queued"
    assert "events" in body["events_url"]

    fetched = await api_client.get(f"/api/v1/analyses/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["deck_id"] == deck_id
    assert fetched.json()["status"] == "queued"


@pytest.mark.asyncio
async def test_unknown_analysis(api_client: AsyncClient) -> None:
    response = await api_client.get(f"/api/v1/analyses/{uuid.uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_analysis_for_unknown_deck(api_client: AsyncClient) -> None:
    response = await api_client.post(
        f"/api/v1/decks/{uuid.uuid4()}/analyses",
        json={"budget_usd": 10, "recommendation_count": 1},
    )
    assert response.status_code == 404
