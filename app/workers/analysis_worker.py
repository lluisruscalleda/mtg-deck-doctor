"""RabbitMQ analysis worker."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from aio_pika.abc import AbstractIncomingMessage

from app.agents.graph import build_analysis_graph, create_chat_model
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.db.models import AnalysisStatus
from app.db.session import close_db, get_session_factory, init_db
from app.messaging.rabbitmq import connect_rabbitmq, declare_analysis_queue
from app.repositories.analyses import AnalysisRepository
from app.repositories.events import EventRepository
from app.services.scryfall import ScryfallClient

logger = get_logger(__name__)

TERMINAL = {AnalysisStatus.COMPLETED.value, AnalysisStatus.FAILED.value}
MAX_TRANSIENT_RETRIES = 3


class PermanentJobError(Exception):
    """Non-retryable job failure."""


def _safe_error(message: str) -> str:
    lowered = message.lower()
    # Scrub only strings that look like embedded credentials / URLs with secrets.
    for secret_marker in ("sk-", "amqp://", "postgresql+asyncpg://", "password=", "api_key="):
        if secret_marker in lowered:
            return "Analysis failed due to a configuration or infrastructure error."
    return message[:500]


async def _fail_analysis(factory: Any, analysis_id: uuid.UUID, message: str) -> None:
    async with factory() as session:
        analyses = AnalysisRepository(session)
        events = EventRepository(session)
        analysis = await analyses.get(analysis_id)
        if analysis is None or analysis.status in TERMINAL:
            return
        safe = _safe_error(message)
        await analyses.mark_failed(analysis, error_message=safe)
        await events.append(
            analysis_id=analysis_id,
            event_type="failed",
            payload={
                "analysis_id": str(analysis_id),
                "status": "failed",
                "error_message": safe,
            },
        )
        await session.commit()


async def process_analysis_job(
    analysis_id: uuid.UUID,
    *,
    settings: Settings | None = None,
    llm: Any | None = None,
    scryfall: ScryfallClient | None = None,
) -> None:
    """Process a single analysis job idempotently."""
    cfg = settings or get_settings()
    factory = get_session_factory()

    async with factory() as session:
        analyses = AnalysisRepository(session)
        events = EventRepository(session)
        analysis = await analyses.get(analysis_id)
        if analysis is None:
            raise PermanentJobError(f"Analysis {analysis_id} not found")
        if analysis.status in TERMINAL:
            logger.info("Skipping already-terminal analysis %s", analysis_id)
            return
        if analysis.status == AnalysisStatus.RUNNING.value:
            logger.warning(
                "Analysis %s already running; acknowledging duplicate delivery",
                analysis_id,
            )
            return

        await analyses.mark_running(analysis)
        await events.append(
            analysis_id=analysis.id,
            event_type="progress",
            payload={"step": "started", "percent": 5, "status": "running"},
        )
        await session.commit()
        deck = analysis.deck
        options = dict(analysis.options)

    owns_scryfall = scryfall is None
    client = scryfall or ScryfallClient(cfg)
    chat_model = llm
    try:
        if chat_model is None:
            chat_model = create_chat_model(cfg)
        if owns_scryfall:
            await client.__aenter__()

        last_percent = 5

        async def on_progress(step: str, percent: int) -> None:
            nonlocal last_percent
            percent = max(last_percent, min(percent, 99))
            last_percent = percent
            async with factory() as progress_session:
                progress_events = EventRepository(progress_session)
                await progress_events.append(
                    analysis_id=analysis_id,
                    event_type="progress",
                    payload={"step": step, "percent": percent},
                )
                await progress_session.commit()

        graph = build_analysis_graph(
            scryfall=client,
            llm=chat_model,
            settings=cfg,
            on_progress=on_progress,
        )
        final_state = await graph.ainvoke(
            {
                "analysis_id": str(analysis_id),
                "deck_id": str(deck.id),
                "format": deck.format,
                "budget_usd": float(options.get("budget_usd", 0)),
                "recommendation_count": int(options.get("recommendation_count", 3)),
                "deck_cards": list(deck.cards),
                "warnings": [],
                "validation_attempts": 0,
            }
        )

        async with factory() as finish_session:
            finish_analyses = AnalysisRepository(finish_session)
            finish_events = EventRepository(finish_session)
            current = await finish_analyses.get(analysis_id)
            if current is None:
                raise PermanentJobError(f"Analysis {analysis_id} disappeared")
            if current.status in TERMINAL:
                return

            error = final_state.get("error")
            result = final_state.get("result")
            metrics = final_state.get("metrics") or {}

            if error and not result:
                await finish_analyses.mark_failed(
                    current, error_message=_safe_error(str(error))
                )
                await finish_events.append(
                    analysis_id=analysis_id,
                    event_type="failed",
                    payload={
                        "analysis_id": str(analysis_id),
                        "status": "failed",
                        "error_message": _safe_error(str(error)),
                    },
                )
            else:
                if result is None:
                    result = {
                        "summary": final_state.get("summary") or "Analysis complete.",
                        "strengths": final_state.get("strengths") or [],
                        "weaknesses": final_state.get("weaknesses") or [],
                        "recommendations": final_state.get("recommendations") or [],
                        "warnings": final_state.get("warnings") or [],
                    }
                await finish_analyses.mark_completed(
                    current, metrics=metrics, result=result
                )
                await finish_events.append(
                    analysis_id=analysis_id,
                    event_type="completed",
                    payload={"analysis_id": str(analysis_id), "status": "completed"},
                )
            await finish_session.commit()
    except PermanentJobError:
        raise
    except RuntimeError as exc:
        await _fail_analysis(factory, analysis_id, str(exc))
        raise PermanentJobError(str(exc)) from exc
    except Exception as exc:
        await _fail_analysis(factory, analysis_id, str(exc))
        raise
    finally:
        if owns_scryfall:
            await client.aclose()


async def handle_message(
    message: AbstractIncomingMessage,
    *,
    settings: Settings,
) -> None:
    try:
        payload = json.loads(message.body.decode("utf-8"))
        analysis_id = uuid.UUID(str(payload["analysis_id"]))
    except Exception:
        logger.exception("Invalid analysis message; rejecting")
        await message.reject(requeue=False)
        return

    try:
        await process_analysis_job(analysis_id, settings=settings)
        await message.ack()
    except PermanentJobError:
        logger.exception("Permanent failure for %s", analysis_id)
        await message.reject(requeue=False)
    except Exception:
        headers = message.headers or {}
        retries = int(headers.get("x-retry", 0))
        if retries < MAX_TRANSIENT_RETRIES:
            logger.exception("Transient failure for %s (retry %s)", analysis_id, retries)
            await message.reject(requeue=True)
        else:
            logger.exception("Exhausted retries for %s", analysis_id)
            await message.reject(requeue=False)


async def run_worker() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    init_db(settings)
    logger.info("Analysis worker started")

    connection = await connect_rabbitmq(settings.rabbitmq_url)
    try:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=1)
        queue = await declare_analysis_queue(channel, settings)

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                try:
                    await handle_message(message, settings=settings)
                except Exception:
                    logger.exception("Unhandled worker error")
    finally:
        await connection.close()
        await close_db()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
