"""Deck request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator


class DeckFormat(StrEnum):
    OLD_SCHOOL_SWEDISH = "old_school_swedish"
    MODERN = "modern"
    COMMANDER = "commander"
    STANDARD = "standard"
    PIONEER = "pioneer"
    LEGACY = "legacy"
    VINTAGE = "vintage"
    PAUPER = "pauper"
    CUSTOM = "custom"


class CardEntry(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    quantity: Annotated[int, Field(ge=1, le=100)]

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Card name cannot be empty")
        return cleaned


class DeckCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    format: DeckFormat
    cards: Annotated[list[CardEntry], Field(min_length=1)]

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Deck name cannot be empty")
        return cleaned

    @model_validator(mode="after")
    def normalize_and_validate_cards(self) -> DeckCreate:
        merged: dict[str, int] = {}
        order: list[str] = []
        for card in self.cards:
            key = card.name.casefold()
            if key not in merged:
                merged[key] = 0
                order.append(card.name)
            # Keep the first-seen casing as the display name key via order list.
            merged[key] += card.quantity

        display_names = {name.casefold(): name for name in order}
        normalized = [
            CardEntry(name=display_names[key], quantity=qty) for key, qty in merged.items()
        ]
        total = sum(c.quantity for c in normalized)
        # Soft max; hard limit enforced with settings in the service layer.
        if total < 1:
            raise ValueError("Deck must contain at least one card")
        self.cards = normalized
        return self


class DeckRead(BaseModel):
    id: uuid.UUID
    name: str
    format: str
    cards: list[CardEntry]
    created_at: datetime
    unresolved_cards: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}
