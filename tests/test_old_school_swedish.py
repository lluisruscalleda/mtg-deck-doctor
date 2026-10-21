"""Old School Swedish format helpers."""

from app.formats.old_school_swedish import (
    OLD_SCHOOL_SWEDISH_DISPLAY_NAME,
    is_banned,
    is_restricted,
    old_school_swedish_prompt_notes,
    old_school_swedish_scryfall_clause,
)
from app.agents.prompts import build_user_prompt
from app.schemas.deck import DeckFormat


def test_display_name_and_enum() -> None:
    assert OLD_SCHOOL_SWEDISH_DISPLAY_NAME == "Old School Swedish"
    assert DeckFormat.OLD_SCHOOL_SWEDISH == "old_school_swedish"


def test_scryfall_clause_covers_swedish_sets() -> None:
    clause = old_school_swedish_scryfall_clause()
    for code in ("lea", "leb", "2ed", "arn", "atq", "leg", "drk", "sum"):
        assert f"e:{code}" in clause
    assert "fem" not in clause  # Fallen Empires is not Swedish OS legal


def test_banned_and_restricted() -> None:
    assert is_banned("Bronze Tablet")
    assert is_banned("contract from below")
    assert not is_banned("Lightning Bolt")
    assert is_restricted("Black Lotus")
    assert is_restricted("Sol Ring")
    assert not is_restricted("Lightning Bolt")


def test_prompt_notes_and_user_prompt_label_old_school_swedish() -> None:
    notes = old_school_swedish_prompt_notes()
    assert "Old School Swedish" in notes
    assert "Banned" in notes
    assert "Restricted" in notes

    prompt = build_user_prompt(
        format_name="old_school_swedish",
        budget_usd=50,
        recommendation_count=2,
        metrics={},
        deck_cards=[{"name": "Lightning Bolt", "quantity": 4}],
        candidates=[
            {
                "name": "Fireball",
                "mana_value": 1,
                "type_line": "Sorcery",
                "price_usd": 1.0,
            }
        ],
        warnings=[],
    )
    assert "Format: Old School Swedish" in prompt
    assert "Legal sets:" in prompt
