"""Deck API tests."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock

import pytest
from app.api.deps import get_scryfall_client
from app.core.exceptions import CardResolutionError
from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.services.scryfall import ResolvedCard, ScryfallClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def _resolved(name: str, **kwargs: Any) -> ResolvedCard:
    data = {
        "id": str(uuid.uuid4()),
        "name": name,
        "cmc": 1,
        "mana_cost": "{R}",
        "type_line": "Instant",
        "colors": ["R"],
        "color_identity": ["R"],
        "prices": {"usd": "0.50"},
        "oracle_text": "text",
    }
    data.update(kwargs)
    return ResolvedCard(data)


class FakeScryfall(ScryfallClient):
    def __init__(self, mapping: dict[str, ResolvedCard | None]) -> None:
        self.mapping = {k.casefold(): v for k, v in mapping.items()}
        self._client = AsyncMock()
        self._owns_client = False

    async def resolve_card_name(self, name: str) -> ResolvedCard:
        card = self.mapping.get(name.casefold())
        if card is None:
            raise CardResolutionError(f"Unknown card: {name}")
        return card

    async def resolve_many(
        self, names: list[str]
    ) -> tuple[dict[str, ResolvedCard], list[str], list[str]]:
        resolved: dict[str, ResolvedCard] = {}
        unresolved: list[str] = []
        warnings: list[str] = []
        for name in names:
            try:
                resolved[name] = await self.resolve_card_name(name)
            except CardResolutionError:
                unresolved.append(name)
                warnings.append(f"Could not resolve card name against Scryfall: {name}")
        return resolved, unresolved, warnings


@pytest.fixture
async def api_client() -> AsyncGenerator[AsyncClient, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    app = create_app()
    fake = FakeScryfall(
        {
            "Lightning Bolt": _resolved("Lightning Bolt"),
            "Mountain": _resolved(
                "Mountain",
                cmc=0,
                mana_cost="",
                type_line="Basic Land — Mountain",
                colors=[],
            ),
            "Monastery Swiftspear": _resolved(
                "Monastery Swiftspear",
                type_line="Creature — Human Monk",
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
async def test_create_and_get_deck(api_client: AsyncClient) -> None:
    payload = {
        "name": "Burn test",
        "format": "modern",
        "cards": [
            {"name": "Lightning Bolt", "quantity": 4},
            {"name": "Monastery Swiftspear", "quantity": 4},
            {"name": "Mountain", "quantity": 20},
        ],
    }
    created = await api_client.post("/api/v1/decks", json=payload)
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "Burn test"
    assert body["format"] == "modern"
    assert len(body["cards"]) == 3

    fetched = await api_client.get(f"/api/v1/decks/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]


@pytest.mark.asyncio
async def test_invalid_payload(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/decks",
        json={"name": "", "format": "modern", "cards": []},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_unknown_deck(api_client: AsyncClient) -> None:
    response = await api_client.get(f"/api/v1/decks/{uuid.uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_duplicate_cards_are_merged(api_client: AsyncClient) -> None:
    payload = {
        "name": "Merge",
        "format": "modern",
        "cards": [
            {"name": "Lightning Bolt", "quantity": 2},
            {"name": "lightning bolt", "quantity": 2},
            {"name": "Mountain", "quantity": 10},
        ],
    }
    response = await api_client.post("/api/v1/decks", json=payload)
    assert response.status_code == 201
    cards = response.json()["cards"]
    bolt = next(c for c in cards if c["name"].casefold() == "lightning bolt")
    assert bolt["quantity"] == 4
