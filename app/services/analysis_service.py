"""Deck and analysis application services."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import CardResolutionError, NotFoundError, ValidationAppError
from app.messaging.outbox import enqueue_outbox
from app.repositories.analyses import AnalysisRepository
from app.repositories.decks import DeckRepository
from app.repositories.events import EventRepository
from app.schemas.analysis import AnalysisCreate
from app.schemas.deck import DeckCreate, DeckRead
from app.services.scryfall import ScryfallClient


class DeckService:
    def __init__(
        self,
        session: AsyncSession,
        scryfall: ScryfallClient,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.scryfall = scryfall
        self.settings = settings or get_settings()
        self.decks = DeckRepository(session)

    async def create_deck(self, payload: DeckCreate) -> DeckRead:
        total = sum(c.quantity for c in payload.cards)
        if total > self.settings.max_cards_per_deck:
            raise ValidationAppError(
                f"Deck exceeds maximum of {self.settings.max_cards_per_deck} cards "
                f"(got {total})"
            )

        for card in payload.cards:
            if len(card.name) > self.settings.max_card_name_length:
                raise ValidationAppError(
                    f"Card name exceeds {self.settings.max_card_name_length} characters: "
                    f"{card.name!r}"
                )

        names = [c.name for c in payload.cards]
        resolved, unresolved, warnings = await self.scryfall.resolve_many(names)

        if unresolved and not resolved:
            raise CardResolutionError(
                "None of the provided card names could be resolved via Scryfall: "
                + ", ".join(unresolved)
            )

        stored_cards = [{"name": c.name, "quantity": c.quantity} for c in payload.cards]
        # Prefer Scryfall canonical names for resolved cards.
        for item in stored_cards:
            card = resolved.get(item["name"])
            if card is not None:
                item["name"] = card.name

        deck = await self.decks.create(
            name=payload.name,
            format=payload.format.value,
            cards=stored_cards,
        )
        await self.session.commit()
        await self.session.refresh(deck)

        if unresolved:
            warnings = [
                *warnings,
                (
                    "Deck saved with unresolved cards; "
                    "metrics and analysis will treat them as unknown."
                ),
            ]

        return DeckRead(
            id=deck.id,
            name=deck.name,
            format=deck.format,
            cards=deck.cards,
            created_at=deck.created_at,
            unresolved_cards=unresolved,
            warnings=warnings,
        )

    async def get_deck(self, deck_id: uuid.UUID) -> DeckRead:
        deck = await self.decks.get(deck_id)
        if deck is None:
            raise NotFoundError(f"Deck {deck_id} not found")
        return DeckRead(
            id=deck.id,
            name=deck.name,
            format=deck.format,
            cards=deck.cards,
            created_at=deck.created_at,
        )


class AnalysisService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.decks = DeckRepository(session)
        self.analyses = AnalysisRepository(session)
        self.events = EventRepository(session)

    async def create_analysis(
        self,
        deck_id: uuid.UUID,
        payload: AnalysisCreate,
    ) -> dict[str, Any]:
        deck = await self.decks.get(deck_id)
        if deck is None:
            raise NotFoundError(f"Deck {deck_id} not found")

        count = min(payload.recommendation_count, self.settings.max_recommendations)
        options = {
            "budget_usd": payload.budget_usd,
            "recommendation_count": count,
        }

        analysis = await self.analyses.create(deck_id=deck.id, options=options)
        await self.events.append(
            analysis_id=analysis.id,
            event_type="queued",
            payload={"status": "queued"},
        )
        await enqueue_outbox(
            self.session,
            analysis_id=analysis.id,
            payload={"analysis_id": str(analysis.id)},
        )
        await self.session.commit()

        return {
            "id": analysis.id,
            "status": analysis.status,
            "events_url": f"/api/v1/analyses/{analysis.id}/events",
        }

    async def get_analysis(self, analysis_id: uuid.UUID) -> Any:
        analysis = await self.analyses.get(analysis_id)
        if analysis is None:
            raise NotFoundError(f"Analysis {analysis_id} not found")
        return analysis
