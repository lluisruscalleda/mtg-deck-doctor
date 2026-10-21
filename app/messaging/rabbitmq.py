"""RabbitMQ connection helpers."""

from __future__ import annotations

import aio_pika
from aio_pika import ExchangeType
from aio_pika.abc import AbstractChannel, AbstractRobustConnection

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


async def connect_rabbitmq(url: str | None = None) -> AbstractRobustConnection:
    settings = get_settings()
    return await aio_pika.connect_robust(url or settings.rabbitmq_url)


async def check_rabbitmq_connectivity(url: str) -> None:
    connection = await aio_pika.connect_robust(url, timeout=5)
    try:
        async with connection:
            channel = await connection.channel()
            await channel.close()
    finally:
        if not connection.is_closed:
            await connection.close()


async def declare_analysis_queue(
    channel: AbstractChannel,
    settings: Settings | None = None,
) -> aio_pika.abc.AbstractQueue:
    """Declare durable analysis queue with a dead-letter queue."""
    cfg = settings or get_settings()
    await channel.declare_exchange("amq.direct", ExchangeType.DIRECT, durable=True)

    await channel.declare_queue(
        cfg.rabbitmq_dlq,
        durable=True,
    )

    queue = await channel.declare_queue(
        cfg.rabbitmq_queue,
        durable=True,
        arguments={
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": cfg.rabbitmq_dlq,
        },
    )
    return queue


async def publish_json(
    channel: AbstractChannel,
    *,
    queue_name: str,
    body: bytes,
    message_id: str | None = None,
) -> None:
    message = aio_pika.Message(
        body=body,
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        content_type="application/json",
        message_id=message_id,
    )
    # Publisher confirms are enabled when channel is opened with publisher_confirms=True.
    await channel.default_exchange.publish(message, routing_key=queue_name)
    logger.info("Published message to %s (id=%s)", queue_name, message_id)
