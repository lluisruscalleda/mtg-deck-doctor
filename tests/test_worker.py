"""Worker idempotency and failure tests."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
from app.agents.schemas import AnalysisLLMResult, Recommendation, RecommendationCategory
from app.db.base import Base
from app.db.models import Analysis, AnalysisStatus, Deck
from app.db.session import close_db
from app.repositories.analyses import AnalysisRepository
from app.workers import analysis_worker
from app.workers.analysis_worker import PermanentJobError, process_analysis_job
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from tests.fakes import DeterministicChatModel, FakeScryfall, make_card


@pytest.fixture
async def worker_env(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[async_sessionmaker, None]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    monkeypatch.setattr(analysis_worker, "get_session_factory", lambda: factory)
    # Also patch module-level close to no-op during tests
    yield factory
    await engine.dispose()
    await close_db()


async def _seed_analysis(factory: async_sessionmaker) -> uuid.UUID:
    async with factory() as session:
        deck = Deck(
            name="Burn",
            format="modern",
            cards=[
                {"name": "Lightning Bolt", "quantity": 4},
                {"name": "Mountain", "quantity": 20},
            ],
        )
        session.add(deck)
        await session.flush()
        analysis = Analysis(
            deck_id=deck.id,
            status=AnalysisStatus.QUEUED.value,
            options={"budget_usd": 30, "recommendation_count": 1},
        )
        session.add(analysis)
        await session.commit()
        return analysis.id


@pytest.mark.asyncio
async def test_worker_completes_and_is_idempotent(worker_env: async_sessionmaker) -> None:
    analysis_id = await _seed_analysis(worker_env)
    scryfall = FakeScryfall(
        {
            "Lightning Bolt": make_card("Lightning Bolt"),
            "Mountain": make_card(
                "Mountain",
                cmc=0,
                type_line="Basic Land — Mountain",
                colors=[],
                prices={"usd": None},
            ),
        }
    )
    scryfall.candidates = [make_card("Skullcrack", cmc=2)]
    llm = DeterministicChatModel(
        result=AnalysisLLMResult(
            summary="Burn plan.",
            strengths=["Speed"],
            weaknesses=["Lifegain"],
            recommendations=[
                Recommendation(
                    card_name="Skullcrack",
                    reason="Beats lifegain",
                    category=RecommendationCategory.INTERACTION,
                )
            ],
        )
    )

    await process_analysis_job(analysis_id, llm=llm, scryfall=scryfall)
    await process_analysis_job(analysis_id, llm=llm, scryfall=scryfall)

    async with worker_env() as session:
        analysis = await AnalysisRepository(session).get(analysis_id)
        assert analysis is not None
        assert analysis.status == AnalysisStatus.COMPLETED.value
        assert analysis.result is not None
        assert analysis.result["recommendations"][0]["card_name"] == "Skullcrack"


@pytest.mark.asyncio
async def test_worker_permanent_failure_marks_failed(
    worker_env: async_sessionmaker,
) -> None:
    analysis_id = await _seed_analysis(worker_env)
    scryfall = FakeScryfall(
        {
            "Lightning Bolt": make_card("Lightning Bolt"),
            "Mountain": make_card("Mountain", type_line="Basic Land — Mountain", colors=[]),
        }
    )

    with pytest.raises(PermanentJobError):
        await process_analysis_job(analysis_id, llm=None, scryfall=scryfall)

    async with worker_env() as session:
        analysis = await AnalysisRepository(session).get(analysis_id)
        assert analysis is not None
        assert analysis.status == AnalysisStatus.FAILED.value
        assert analysis.error_message
