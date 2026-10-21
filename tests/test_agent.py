"""Agent grounding and fake LLM tests."""

from __future__ import annotations

import pytest
from app.agents.graph import build_analysis_graph
from app.agents.nodes import ground_recommendations
from app.agents.schemas import AnalysisLLMResult, Recommendation, RecommendationCategory

from tests.fakes import DeterministicChatModel, FakeScryfall, make_card


def test_ground_recommendations_filters_invented_cards() -> None:
    result = AnalysisLLMResult(
        summary="Test",
        strengths=["Fast"],
        weaknesses=["Fragile"],
        recommendations=[
            Recommendation(
                card_name="Lightning Bolt",
                reason="Efficient burn",
                category=RecommendationCategory.THREAT,
                estimated_price_usd=99,
            ),
            Recommendation(
                card_name="Invented Dragon",
                reason="Made up",
                category=RecommendationCategory.OTHER,
            ),
        ],
    )
    candidates = [
        {
            "name": "Lightning Bolt",
            "price_usd": 1.25,
            "mana_value": 1,
            "type_line": "Instant",
        }
    ]
    grounded = ground_recommendations(result, candidates, budget_usd=30, max_count=3)
    assert len(grounded.recommendations) == 1
    assert grounded.recommendations[0].card_name == "Lightning Bolt"
    assert grounded.recommendations[0].estimated_price_usd == 1.25
    assert any("Invented Dragon" in w for w in grounded.warnings)


def test_missing_price_warning() -> None:
    result = AnalysisLLMResult(
        summary="Test",
        recommendations=[
            Recommendation(
                card_name="Mountain",
                reason="Land",
                category=RecommendationCategory.MANA,
            )
        ],
    )
    grounded = ground_recommendations(
        result,
        [{"name": "Mountain", "price_usd": None}],
        budget_usd=10,
        max_count=1,
    )
    assert grounded.recommendations[0].estimated_price_usd is None
    assert any("Price unavailable" in w for w in grounded.warnings)


@pytest.mark.asyncio
async def test_graph_with_fake_llm() -> None:
    scryfall = FakeScryfall(
        {
            "Lightning Bolt": make_card("Lightning Bolt"),
            "Mountain": make_card(
                "Mountain",
                cmc=0,
                mana_cost="",
                type_line="Basic Land — Mountain",
                colors=[],
                prices={"usd": None},
            ),
        }
    )
    scryfall.candidates = [
        make_card("Skullcrack", cmc=2, mana_cost="{1}{R}", type_line="Instant")
    ]
    llm = DeterministicChatModel(
        result=AnalysisLLMResult(
            summary="Aggressive burn deck.",
            strengths=["Low curve"],
            weaknesses=["Narrow answers"],
            recommendations=[
                Recommendation(
                    card_name="Skullcrack",
                    reason="Stops lifegain",
                    category=RecommendationCategory.INTERACTION,
                    estimated_price_usd=1.0,
                )
            ],
            warnings=[],
        )
    )
    graph = build_analysis_graph(scryfall=scryfall, llm=llm)
    final = await graph.ainvoke(
        {
            "analysis_id": "a",
            "deck_id": "d",
            "format": "modern",
            "budget_usd": 30.0,
            "recommendation_count": 3,
            "deck_cards": [
                {"name": "Lightning Bolt", "quantity": 4},
                {"name": "Mountain", "quantity": 20},
            ],
            "warnings": [],
            "validation_attempts": 0,
        }
    )
    assert final["result"]["summary"].startswith("Aggressive")
    assert final["result"]["recommendations"][0]["card_name"] == "Skullcrack"
    assert final["metrics"]["total_cards"] == 24
