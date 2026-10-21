"""Analysis API routes including SSE."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import StreamingResponse

from app.api.deps import get_analysis_service
from app.core.config import Settings, get_settings
from app.db.models import AnalysisStatus
from app.db.session import get_session_factory
from app.repositories.analyses import AnalysisRepository
from app.repositories.events import EventRepository
from app.schemas.analysis import AnalysisRead
from app.services.analysis_service import AnalysisService

router = APIRouter(tags=["analyses"])

TERMINAL_EVENTS = {"completed", "failed"}
TERMINAL_STATUS = {AnalysisStatus.COMPLETED.value, AnalysisStatus.FAILED.value}


@router.get("/analyses/{analysis_id}", response_model=AnalysisRead)
async def get_analysis(
    analysis_id: uuid.UUID,
    service: AnalysisService = Depends(get_analysis_service),
) -> AnalysisRead:
    analysis = await service.get_analysis(analysis_id)
    return AnalysisRead(
        id=analysis.id,
        deck_id=analysis.deck_id,
        status=analysis.status,
        options=analysis.options,
        metrics=analysis.metrics,
        result=analysis.result,
        error_message=analysis.error_message,
        created_at=analysis.created_at,
        started_at=analysis.started_at,
        completed_at=analysis.completed_at,
        events_url=f"/api/v1/analyses/{analysis.id}/events",
    )


@router.get("/analyses/{analysis_id}/events")
async def stream_analysis_events(
    analysis_id: uuid.UUID,
    request: Request,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    service: AnalysisService = Depends(get_analysis_service),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    # Validate existence before opening the stream.
    await service.get_analysis(analysis_id)

    try:
        after_id = int(last_event_id) if last_event_id else 0
    except ValueError:
        after_id = 0

    async def event_generator() -> AsyncIterator[str]:
        nonlocal after_id
        factory = get_session_factory()
        terminal_sent = False
        heartbeat_ticks = 0

        while not terminal_sent:
            if await request.is_disconnected():
                break

            async with factory() as session:
                events_repo = EventRepository(session)
                events = await events_repo.list_after(analysis_id, after_id=after_id)
                analyses = AnalysisRepository(session)
                current = await analyses.get(analysis_id)

            if events:
                for event in events:
                    after_id = event.id
                    data = json.dumps(event.payload, default=str)
                    yield f"id: {event.id}\nevent: {event.event_type}\ndata: {data}\n\n"
                    if event.event_type in TERMINAL_EVENTS:
                        terminal_sent = True
                        break
                continue

            if current is not None and current.status in TERMINAL_STATUS:
                break

            heartbeat_ticks += 1
            elapsed = heartbeat_ticks * settings.sse_poll_interval_seconds
            if elapsed >= settings.sse_heartbeat_seconds:
                yield ": heartbeat\n\n"
                heartbeat_ticks = 0

            await asyncio.sleep(settings.sse_poll_interval_seconds)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
        status_code=status.HTTP_200_OK,
    )
