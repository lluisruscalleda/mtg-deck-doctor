"""Transactional outbox helpers and publisher loop."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.db.models import OutboxMessage
from app.messaging.rabbitmq import connect_rabbitmq, declare_analysis_queue, publish_json

logger = get_logger(__name__)


async def enqueue_outbox(
    session: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    payload: dict[str, Any],
) -> OutboxMessage:
    message = OutboxMessage(analysis_id=analysis_id, payload=payload)
    session.add(message)
    await session.flush()
    return message


async def fetch_unpublished(
    session: AsyncSession,
    *,
    batch_size: int,
) -> list[OutboxMessage]:
    stmt = (
        select(OutboxMessage)
        .where(OutboxMessage.published_at.is_(None))
        .order_by(OutboxMessage.created_at.asc())
        .limit(batch_size)
    )
    # SKIP LOCKED is Postgres-specific; fall back for SQLite tests.
    try:
        result = await session.execute(stmt.with_for_update(skip_locked=True))
    except Exception:
        result = await session.execute(stmt)
    return list(result.scalars().all())


async def mark_published(session: AsyncSession, message: OutboxMessage) -> None:
    message.published_at = datetime.now(UTC)
    await session.flush()


async def publish_pending_batch(
    session: AsyncSession,
    *,
    settings: Settings | None = None,
) -> int:
    """Publish a batch of outbox messages. Returns count published."""
    cfg = settings or get_settings()
    messages = await fetch_unpublished(session, batch_size=cfg.outbox_batch_size)
    if not messages:
        return 0

    connection = await connect_rabbitmq(cfg.rabbitmq_url)
    published = 0
    try:
        channel = await connection.channel(publisher_confirms=True)
        await declare_analysis_queue(channel, cfg)
        for message in messages:
            message.attempts += 1
            body = json.dumps(message.payload).encode("utf-8")
            await publish_json(
                channel,
                queue_name=cfg.rabbitmq_queue,
                body=body,
                message_id=str(message.id),
            )
            await mark_published(session, message)
            published += 1
        await session.commit()
    except Exception:
        await session.rollback()
        logger.exception("Outbox publish batch failed")
        raise
    finally:
        await connection.close()

    logger.info("Published %s outbox message(s)", published)
    return published
