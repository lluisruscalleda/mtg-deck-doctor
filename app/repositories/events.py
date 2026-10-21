"""Analysis event persistence."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AnalysisEvent


class EventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def append(
        self,
        *,
        analysis_id: uuid.UUID,
        event_type: str,
        payload: dict[str, Any],
    ) -> AnalysisEvent:
        event = AnalysisEvent(
            analysis_id=analysis_id,
            event_type=event_type,
            payload=payload,
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def list_after(
        self,
        analysis_id: uuid.UUID,
        *,
        after_id: int = 0,
        limit: int = 100,
    ) -> list[AnalysisEvent]:
        result = await self.session.execute(
            select(AnalysisEvent)
            .where(
                AnalysisEvent.analysis_id == analysis_id,
                AnalysisEvent.id > after_id,
            )
            .order_by(AnalysisEvent.id.asc())
            .limit(limit)
        )
        return list(result.scalars().all())
