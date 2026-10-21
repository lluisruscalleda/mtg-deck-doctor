"""Deterministic deck metric calculations."""

from __future__ import annotations

from typing import Any

from app.services.scryfall import ResolvedCard


def calculate_deck_metrics(
    cards: list[dict[str, Any]],
    resolved: dict[str, ResolvedCard],
) -> tuple[dict[str, Any], list[str]]:
    """
    Calculate objective deck statistics.

    `cards` entries: {"name": str, "quantity": int}
    `resolved` maps original card name -> ResolvedCard for known cards.

    Unknown cards are excluded from mana-value averages and noted in warnings.
    Multi-face mana value uses ResolvedCard.mana_value_for_metrics().
    """
    warnings: list[str] = []
    total_cards = 0
    land_count = 0
    nonland_count = 0
    mana_values: list[float] = []
    curve: dict[str, int] = {str(i): 0 for i in range(6)}
    curve["6+"] = 0
    color_dist: dict[str, int] = {"W": 0, "U": 0, "B": 0, "R": 0, "G": 0, "C": 0}
    type_counts: dict[str, int] = {}

    for entry in cards:
        name = entry["name"]
        qty = int(entry["quantity"])
        total_cards += qty
        card = resolved.get(name)
        if card is None:
            # Try case-insensitive match
            card = next(
                (resolved[k] for k in resolved if k.casefold() == name.casefold()),
                None,
            )
        if card is None:
            warnings.append(f"Excluded unresolved card from detailed metrics: {name} x{qty}")
            continue

        if card.is_land:
            land_count += qty
        else:
            nonland_count += qty

        primary = card.primary_type
        type_counts[primary] = type_counts.get(primary, 0) + qty

        colors = card.colors or []
        if not colors:
            color_dist["C"] += qty
        else:
            for color in colors:
                if color in color_dist:
                    color_dist[color] += qty

        if card.is_land:
            continue

        mv = card.mana_value_for_metrics()
        if mv is None:
            warnings.append(f"Missing mana value for nonland card: {card.name}")
            continue

        mana_values.extend([mv] * qty)
        bucket = "6+" if mv >= 6 else str(int(mv))
        if bucket not in curve:
            bucket = "6+"
        curve[bucket] += qty

    avg_mv: float | None
    if mana_values:
        avg_mv = round(sum(mana_values) / len(mana_values), 3)
    else:
        avg_mv = None
        if nonland_count > 0:
            warnings.append("Average mana value unavailable: no usable mana values for nonlands")

    metrics = {
        "total_cards": total_cards,
        "land_count": land_count,
        "nonland_count": nonland_count,
        "average_mana_value": avg_mv,
        "mana_curve": curve,
        "color_distribution": color_dist,
        "type_counts": type_counts,
        "resolved_cards": len(resolved),
    }
    return metrics, warnings
