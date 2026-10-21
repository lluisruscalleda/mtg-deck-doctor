"""FastAPI dependencies."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.services.analysis_service import AnalysisService, DeckService
from app.services.scryfall import ScryfallClient


async def get_scryfall_client() -> AsyncGenerator[ScryfallClient, None]:
    async with ScryfallClient() as client:
        yield client


async def get_deck_service(
    session: AsyncSession = Depends(get_db_session),
    scryfall: ScryfallClient = Depends(get_scryfall_client),
    settings: Settings = Depends(get_settings),
) -> DeckService:
    return DeckService(session, scryfall, settings)


async def get_analysis_service(
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> AnalysisService:
    return AnalysisService(session, settings)
