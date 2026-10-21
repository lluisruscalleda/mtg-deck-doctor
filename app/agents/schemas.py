"""Structured LLM output schemas."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field


class RecommendationCategory(StrEnum):
    CONSISTENCY = "consistency"
    THREAT = "threat"
    INTERACTION = "interaction"
    MANA = "mana"
    DRAW = "draw"
    REMOVAL = "removal"
    OTHER = "other"


class Recommendation(BaseModel):
    card_name: Annotated[str, Field(min_length=1)]
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    category: RecommendationCategory = RecommendationCategory.OTHER
    estimated_price_usd: float | None = None


class AnalysisLLMResult(BaseModel):
    summary: Annotated[str, Field(min_length=1, max_length=2000)]
    strengths: list[Annotated[str, Field(min_length=1)]] = Field(default_factory=list)
    weaknesses: list[Annotated[str, Field(min_length=1)]] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
