"""Unit tests for deterministic deck metrics."""

from __future__ import annotations

from app.services.deck_metrics import calculate_deck_metrics
from app.services.scryfall import ResolvedCard


def _card(**kwargs: object) -> ResolvedCard:
    base = {
        "id": "1",
        "name": "Test",
        "cmc": 1,
        "mana_cost": "{R}",
        "type_line": "Instant",
        "colors": ["R"],
        "color_identity": ["R"],
        "prices": {"usd": "1.00"},
        "oracle_text": "Deal 3 damage.",
    }
    base.update(kwargs)
    return ResolvedCard(base)  # type: ignore[arg-type]


def test_basic_metrics() -> None:
    cards = [
        {"name": "Lightning Bolt", "quantity": 4},
        {"name": "Mountain", "quantity": 20},
    ]
    resolved = {
        "Lightning Bolt": _card(name="Lightning Bolt", cmc=1, type_line="Instant", colors=["R"]),
        "Mountain": _card(
            name="Mountain",
            cmc=0,
            mana_cost="",
            type_line="Basic Land — Mountain",
            colors=[],
        ),
    }
    metrics, warnings = calculate_deck_metrics(cards, resolved)
    assert metrics["total_cards"] == 24
    assert metrics["land_count"] == 20
    assert metrics["nonland_count"] == 4
    assert metrics["average_mana_value"] == 1.0
    assert metrics["mana_curve"]["1"] == 4
    assert metrics["color_distribution"]["R"] == 4
    assert metrics["color_distribution"]["C"] == 20
    assert warnings == []


def test_unknown_cards_produce_warnings() -> None:
    cards = [{"name": "Fake Card", "quantity": 2}, {"name": "Bolt", "quantity": 1}]
    resolved = {"Bolt": _card(name="Bolt", cmc=1)}
    metrics, warnings = calculate_deck_metrics(cards, resolved)
    assert metrics["total_cards"] == 3
    assert metrics["nonland_count"] == 1
    assert any("Fake Card" in w for w in warnings)


def test_missing_mana_value_excluded_from_average() -> None:
    cards = [{"name": "Weird", "quantity": 2}]
    resolved = {
        "Weird": _card(name="Weird", cmc=None, mana_cost=None, type_line="Creature — Weird"),
    }
    metrics, warnings = calculate_deck_metrics(cards, resolved)
    assert metrics["average_mana_value"] is None
    assert any("Missing mana value" in w for w in warnings)


def test_mana_curve_six_plus_bucket() -> None:
    cards = [{"name": "Big", "quantity": 3}]
    resolved = {"Big": _card(name="Big", cmc=7, type_line="Creature — Giant")}
    metrics, _ = calculate_deck_metrics(cards, resolved)
    assert metrics["mana_curve"]["6+"] == 3


def test_multiface_uses_top_level_cmc() -> None:
    card = _card(
        name="Delver of Secrets // Insectile Aberration",
        cmc=1,
        type_line="Creature — Human Wizard // Creature — Insect Horror",
        card_faces=[{"cmc": 1}, {"cmc": 0}],
    )
    metrics, _ = calculate_deck_metrics(
        [{"name": card.name, "quantity": 1}],
        {card.name: card},
    )
    assert metrics["average_mana_value"] == 1.0
