"""Deck API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status

from app.api.deps import get_analysis_service, get_deck_service
from app.schemas.analysis import AnalysisCreate, AnalysisCreated
from app.schemas.deck import DeckCreate, DeckRead
from app.services.analysis_service import AnalysisService, DeckService

router = APIRouter(tags=["decks"])


@router.post("/decks", response_model=DeckRead, status_code=status.HTTP_201_CREATED)
async def create_deck(
    payload: DeckCreate,
    service: DeckService = Depends(get_deck_service),
) -> DeckRead:
    return await service.create_deck(payload)


@router.get("/decks/{deck_id}", response_model=DeckRead)
async def get_deck(
    deck_id: uuid.UUID,
    service: DeckService = Depends(get_deck_service),
) -> DeckRead:
    return await service.get_deck(deck_id)


@router.post(
    "/decks/{deck_id}/analyses",
    response_model=AnalysisCreated,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_analysis(
    deck_id: uuid.UUID,
    payload: AnalysisCreate,
    service: AnalysisService = Depends(get_analysis_service),
) -> AnalysisCreated:
    result = await service.create_analysis(deck_id, payload)
    return AnalysisCreated(**result)
