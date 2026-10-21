"""Outbox publisher process."""

from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import close_db, get_session_factory, init_db
from app.messaging.outbox import publish_pending_batch

logger = get_logger(__name__)


async def run_publisher() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    init_db(settings)
    logger.info("Outbox publisher started")
    try:
        factory = get_session_factory()
        while True:
            try:
                async with factory() as session:
                    await publish_pending_batch(session, settings=settings)
            except Exception:
                logger.exception("Outbox publisher iteration failed; will retry")
            await asyncio.sleep(settings.outbox_poll_interval_seconds)
    finally:
        await close_db()


def main() -> None:
    asyncio.run(run_publisher())


if __name__ == "__main__":
    main()
