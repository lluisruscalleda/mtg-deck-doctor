"""Prompt templates for grounded deck analysis."""

from app.formats.old_school_swedish import (
    OLD_SCHOOL_SWEDISH_DISPLAY_NAME,
    old_school_swedish_prompt_notes,
)

SYSTEM_PROMPT = """You are MTG Deck Doctor, an assistant that analyzes Magic: The Gathering decks.

Rules you must follow:
- Only recommend cards from the provided candidate list. Never invent card names.
- Base strengths, weaknesses, and reasons only on supplied deck cards, metrics, and candidates.
- Do not claim format legality; legality is not verified unless format notes say otherwise.
- When the format is Old School Swedish, respect the supplied Swedish OS set pool and B&R notes.
- If price data is missing, set estimated_price_usd to null and mention the limitation in warnings.
- Keep the summary concise and practical.
- Return structured JSON matching the required schema.
"""


def _format_label(format_name: str) -> str:
    key = format_name.casefold().strip()
    if key == "old_school_swedish":
        return OLD_SCHOOL_SWEDISH_DISPLAY_NAME
    return format_name


def _format_notes(format_name: str) -> str:
    if format_name.casefold().strip() == "old_school_swedish":
        return old_school_swedish_prompt_notes()
    return ""


def build_user_prompt(
    *,
    format_name: str,
    budget_usd: float,
    recommendation_count: int,
    metrics: dict,
    deck_cards: list[dict],
    candidates: list[dict],
    warnings: list[str],
) -> str:
    candidate_lines = []
    for card in candidates:
        price = card.get("price_usd")
        price_txt = f"${price}" if price is not None else "price unknown"
        candidate_lines.append(
            f"- {card['name']} | MV={card.get('mana_value')} | "
            f"{card.get('type_line')} | {price_txt}"
        )

    deck_lines = [
        f"- {c.get('quantity')}x {c.get('name')}" for c in deck_cards
    ]

    notes = _format_notes(format_name)
    notes_block = f"\n{notes}\n" if notes else "\n"

    return (
        f"Format: {_format_label(format_name)}\n"
        f"Budget USD: {budget_usd}\n"
        f"Requested recommendations: {recommendation_count}\n"
        + notes_block
        + "\nExisting warnings:\n"
        + ("\n".join(f"- {w}" for w in warnings) or "- none")
        + "\n\nMetrics JSON:\n"
        + str(metrics)
        + "\n\nDeck list:\n"
        + "\n".join(deck_lines)
        + "\n\nCandidate cards (recommend ONLY from this list):\n"
        + "\n".join(candidate_lines)
        + "\n\nProduce a grounded analysis."
    )
