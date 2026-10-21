"""Deterministic fakes for tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from app.agents.schemas import AnalysisLLMResult
from app.core.exceptions import CardResolutionError
from app.services.scryfall import ResolvedCard, ScryfallClient
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda


class DeterministicChatModel(BaseChatModel):
    """Chat model that returns a fixed structured AnalysisLLMResult."""

    result: AnalysisLLMResult

    @property
    def _llm_type(self) -> str:
        return "deterministic-fake"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        content = self.result.model_dump_json()
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])

    def with_structured_output(self, schema: type[AnalysisLLMResult], **kwargs: Any):  # type: ignore[override]
        async def _run(_input: Any) -> AnalysisLLMResult:
            return self.result

        return RunnableLambda(_run)


class FakeScryfall(ScryfallClient):
    def __init__(self, cards: dict[str, ResolvedCard] | None = None) -> None:
        self.cards = {k.casefold(): v for k, v in (cards or {}).items()}
        self._client = AsyncMock()
        self._owns_client = False
        self.candidates: list[ResolvedCard] = []

    async def resolve_card_name(self, name: str) -> ResolvedCard:
        card = self.cards.get(name.casefold())
        if card is None:
            raise CardResolutionError(f"Unknown card: {name}")
        return card

    async def resolve_many(self, names: list[str]):
        resolved: dict[str, ResolvedCard] = {}
        unresolved: list[str] = []
        warnings: list[str] = []
        for name in names:
            try:
                resolved[name] = await self.resolve_card_name(name)
            except CardResolutionError:
                unresolved.append(name)
                warnings.append(f"Could not resolve card name against Scryfall: {name}")
        return resolved, unresolved, warnings

    async def search_candidates(
        self, *, colors, format_name="old_school_swedish", query_extra="", limit=20
    ):
        return self.candidates[:limit]


def make_card(name: str, **kwargs: Any) -> ResolvedCard:
    data = {
        "id": name,
        "name": name,
        "cmc": 1,
        "mana_cost": "{R}",
        "type_line": "Instant",
        "colors": ["R"],
        "color_identity": ["R"],
        "prices": {"usd": "1.00"},
        "oracle_text": "text",
    }
    data.update(kwargs)
    return ResolvedCard(data)
