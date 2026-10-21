"""Analysis persistence."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Analysis, AnalysisStatus


class AnalysisRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        deck_id: uuid.UUID,
        options: dict[str, Any],
    ) -> Analysis:
        analysis = Analysis(
            deck_id=deck_id,
            status=AnalysisStatus.QUEUED.value,
            options=options,
        )
        self.session.add(analysis)
        await self.session.flush()
        return analysis

    async def get(self, analysis_id: uuid.UUID) -> Analysis | None:
        result = await self.session.execute(
            select(Analysis)
            .where(Analysis.id == analysis_id)
            .options(selectinload(Analysis.deck))
        )
        return result.scalar_one_or_none()

    async def mark_running(self, analysis: Analysis) -> Analysis:
        analysis.status = AnalysisStatus.RUNNING.value
        analysis.started_at = datetime.now(UTC)
        analysis.error_message = None
        await self.session.flush()
        return analysis

    async def mark_completed(
        self,
        analysis: Analysis,
        *,
        metrics: dict[str, Any],
        result: dict[str, Any],
    ) -> Analysis:
        analysis.status = AnalysisStatus.COMPLETED.value
        analysis.metrics = metrics
        analysis.result = result
        analysis.completed_at = datetime.now(UTC)
        analysis.error_message = None
        await self.session.flush()
        return analysis

    async def mark_failed(self, analysis: Analysis, *, error_message: str) -> Analysis:
        analysis.status = AnalysisStatus.FAILED.value
        analysis.error_message = error_message
        analysis.completed_at = datetime.now(UTC)
        await self.session.flush()
        return analysis
