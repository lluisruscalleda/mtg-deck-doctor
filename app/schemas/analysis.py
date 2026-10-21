"""Analysis request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, Field


class AnalysisCreate(BaseModel):
    budget_usd: Annotated[float, Field(ge=0, le=100_000)] = 50.0
    recommendation_count: Annotated[int, Field(ge=1, le=10)] = 3


class AnalysisRead(BaseModel):
    id: uuid.UUID
    deck_id: uuid.UUID
    status: str
    options: dict[str, Any]
    metrics: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    events_url: str | None = None

    model_config = {"from_attributes": True}


class AnalysisCreated(BaseModel):
    id: uuid.UUID
    status: str
    events_url: str
