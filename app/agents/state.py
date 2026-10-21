"""LangGraph typed state."""

from __future__ import annotations

from typing import Any, TypedDict


class AnalysisGraphState(TypedDict, total=False):
    analysis_id: str
    deck_id: str
    format: str
    budget_usd: float
    recommendation_count: int
    card_data: list[dict[str, Any]]
    deck_cards: list[dict[str, Any]]
    candidates: list[dict[str, Any]]
    warnings: list[str]
    metrics: dict[str, Any]
    recommendations: list[dict[str, Any]]
    summary: str
    strengths: list[str]
    weaknesses: list[str]
    result: dict[str, Any]
    error: str | None
    validation_attempts: int
