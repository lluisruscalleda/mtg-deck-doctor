"""LangGraph node implementations."""

from __future__ import annotations

import json
from typing import Any, Protocol

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.prompts import SYSTEM_PROMPT, build_user_prompt
from app.agents.schemas import AnalysisLLMResult
from app.agents.state import AnalysisGraphState
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.services.deck_metrics import calculate_deck_metrics
from app.services.scryfall import ResolvedCard, ScryfallClient

logger = get_logger(__name__)


class ProgressCallback(Protocol):
    async def __call__(self, step: str, percent: int) -> None: ...


def _candidate_name_set(candidates: list[dict[str, Any]]) -> set[str]:
    return {c["name"].casefold() for c in candidates}


def ground_recommendations(
    result: AnalysisLLMResult,
    candidates: list[dict[str, Any]],
    *,
    budget_usd: float,
    max_count: int,
) -> AnalysisLLMResult:
    """Filter LLM recommendations to verified candidates and budget honesty."""
    by_name = {c["name"].casefold(): c for c in candidates}
    grounded = []
    warnings = list(result.warnings)

    for rec in result.recommendations:
        key = rec.card_name.casefold()
        candidate = by_name.get(key)
        if candidate is None:
            warnings.append(f"Dropped ungounded recommendation: {rec.card_name}")
            continue

        price = candidate.get("price_usd")
        estimated = price if isinstance(price, (int, float)) else None
        if estimated is None:
            warnings.append(
                f"Price unavailable for {candidate['name']}; budget fit not guaranteed."
            )
        elif estimated > budget_usd:
            warnings.append(
                f"{candidate['name']} exceeds budget (${estimated} > ${budget_usd})."
            )

        grounded.append(
            rec.model_copy(
                update={
                    "card_name": candidate["name"],
                    "estimated_price_usd": estimated,
                }
            )
        )
        if len(grounded) >= max_count:
            break

    if len(grounded) < max_count:
        warnings.append(
            f"Only {len(grounded)} grounded recommendation(s) available "
            f"(requested {max_count})."
        )

    return result.model_copy(update={"recommendations": grounded, "warnings": warnings})


class AnalysisNodes:
    def __init__(
        self,
        *,
        scryfall: ScryfallClient,
        llm: BaseChatModel | None,
        settings: Settings | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        self.scryfall = scryfall
        self.llm = llm
        self.settings = settings or get_settings()
        self.on_progress = on_progress

    async def _progress(self, step: str, percent: int) -> None:
        if self.on_progress is not None:
            await self.on_progress(step, percent)

    async def fetch_cards(self, state: AnalysisGraphState) -> AnalysisGraphState:
        await self._progress("fetch_cards", 20)
        deck_cards = list(state.get("deck_cards") or [])
        names = [str(c["name"]) for c in deck_cards]
        resolved, unresolved, warnings = await self.scryfall.resolve_many(names)
        card_data = []
        for entry in deck_cards:
            card = resolved.get(entry["name"])
            if card is None:
                continue
            payload = card.to_dict()
            payload["quantity"] = entry["quantity"]
            card_data.append(payload)

        colors: list[str] = []
        for card in resolved.values():
            colors.extend(card.color_identity or card.colors or [])

        candidates_raw = await self.scryfall.search_candidates(
            colors=colors,
            format_name=str(state.get("format") or "old_school_swedish"),
            limit=25,
        )
        deck_names = {c.name.casefold() for c in resolved.values()}
        candidates = [
            c.to_dict()
            for c in candidates_raw
            if c.name.casefold() not in deck_names
        ]

        merged_warnings = list(state.get("warnings") or []) + warnings
        if unresolved:
            merged_warnings.append(
                "Some cards remain unresolved and were excluded from analysis details."
            )

        return {
            **state,
            "card_data": card_data,
            "candidates": candidates,
            "warnings": merged_warnings,
            "error": None,
        }

    async def calculate_metrics(self, state: AnalysisGraphState) -> AnalysisGraphState:
        await self._progress("calculate_metrics", 45)
        deck_cards = list(state.get("deck_cards") or [])
        resolved_map: dict[str, ResolvedCard] = {}
        for item in state.get("card_data") or []:
            resolved_map[item["name"]] = ResolvedCard(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "cmc": item.get("cmc"),
                    "mana_cost": item.get("mana_cost"),
                    "type_line": item.get("type_line"),
                    "oracle_text": item.get("oracle_text"),
                    "colors": item.get("colors") or [],
                    "color_identity": item.get("color_identity") or [],
                    "prices": {"usd": item.get("price_usd")},
                    "layout": item.get("layout"),
                }
            )
        metrics, warnings = calculate_deck_metrics(deck_cards, resolved_map)
        return {
            **state,
            "metrics": metrics,
            "warnings": list(state.get("warnings") or []) + warnings,
        }

    async def generate_recommendations(
        self, state: AnalysisGraphState
    ) -> AnalysisGraphState:
        await self._progress("generate_recommendations", 75)
        if self.llm is None:
            return {
                **state,
                "error": "LLM is not configured. Set LLM_API_KEY to enable recommendations.",
            }

        prompt = build_user_prompt(
            format_name=str(state.get("format")),
            budget_usd=float(state.get("budget_usd") or 0),
            recommendation_count=int(state.get("recommendation_count") or 3),
            metrics=dict(state.get("metrics") or {}),
            deck_cards=list(state.get("deck_cards") or []),
            candidates=list(state.get("candidates") or []),
            warnings=list(state.get("warnings") or []),
        )

        # DeepSeek rejects response_format type "json_schema" ("unavailable now").
        # Function calling still enforces AnalysisLLMResult on OpenAI-compatible APIs.
        structured = self.llm.with_structured_output(
            AnalysisLLMResult,
            method="function_calling",
        )
        raw = await structured.ainvoke(
            [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)]
        )
        if isinstance(raw, AnalysisLLMResult):
            parsed = raw
        elif isinstance(raw, dict):
            parsed = AnalysisLLMResult.model_validate(raw)
        else:
            parsed = AnalysisLLMResult.model_validate(json.loads(str(raw)))

        return {
            **state,
            "summary": parsed.summary,
            "strengths": parsed.strengths,
            "weaknesses": parsed.weaknesses,
            "recommendations": [r.model_dump() for r in parsed.recommendations],
            "warnings": list(state.get("warnings") or []) + list(parsed.warnings),
            "error": None,
        }

    async def validate_output(self, state: AnalysisGraphState) -> AnalysisGraphState:
        await self._progress("validate_output", 90)
        attempts = int(state.get("validation_attempts") or 0) + 1
        candidates = list(state.get("candidates") or [])
        try:
            parsed = AnalysisLLMResult(
                summary=str(state.get("summary") or ""),
                strengths=list(state.get("strengths") or []),
                weaknesses=list(state.get("weaknesses") or []),
                recommendations=list(state.get("recommendations") or []),
                warnings=list(state.get("warnings") or []),
            )
            grounded = ground_recommendations(
                parsed,
                candidates,
                budget_usd=float(state.get("budget_usd") or 0),
                max_count=int(state.get("recommendation_count") or 3),
            )
            result = grounded.model_dump()
            return {
                **state,
                "result": result,
                "recommendations": result["recommendations"],
                "warnings": result["warnings"],
                "validation_attempts": attempts,
                "error": None,
            }
        except Exception as exc:
            logger.warning("Validation failed: %s", exc)
            return {
                **state,
                "validation_attempts": attempts,
                "error": f"Output validation failed: {exc}",
            }

    async def persist_result(self, state: AnalysisGraphState) -> AnalysisGraphState:
        # Persistence is handled by the worker after the graph returns.
        await self._progress("persist_result", 95)
        return state


def should_retry_validation(state: AnalysisGraphState) -> str:
    settings = get_settings()
    attempts = int(state.get("validation_attempts") or 0)
    if state.get("error") and attempts <= settings.llm_max_retries:
        return "generate_recommendations"
    return "persist_result"
