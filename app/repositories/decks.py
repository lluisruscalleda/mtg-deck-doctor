"""Deck persistence."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Deck


class DeckRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        name: str,
        format: str,
        cards: list[dict[str, Any]],
    ) -> Deck:
        deck = Deck(name=name, format=format, cards=cards)
        self.session.add(deck)
        await self.session.flush()
        return deck

    async def get(self, deck_id: uuid.UUID) -> Deck | None:
        result = await self.session.execute(select(Deck).where(Deck.id == deck_id))
        return result.scalar_one_or_none()
