"""Old School Swedish (Swedish OS) card pool and B&R.

Source: https://ragingbullseries.com/index.php/swedish-os-rules/
(B&R also tracked at http://oldschool-mtg.blogspot.com/p/banrestriction.html)
"""

from __future__ import annotations

OLD_SCHOOL_SWEDISH_DISPLAY_NAME = "Old School Swedish"

# Scryfall set codes for Swedish OS legal sets.
LEGAL_SET_CODES: tuple[str, ...] = (
    "lea",  # Alpha
    "leb",  # Beta
    "2ed",  # Unlimited
    "arn",  # Arabian Nights
    "atq",  # Antiquities
    "leg",  # Legends
    "drk",  # The Dark
    "sum",  # Edgar / Summer Magic
)

LEGAL_SET_NAMES: tuple[str, ...] = (
    "Alpha",
    "Beta",
    "Unlimited",
    "Arabian Nights",
    "Antiquities",
    "Legends",
    "The Dark",
    "Edgar/Summer",
)

# Ante cards are banned unless the event is played for ante.
BANNED_CARDS: frozenset[str] = frozenset(
    {
        "Bronze Tablet",
        "Contract from Below",
        "Darkpact",
        "Demonic Attorney",
        "Jeweled Bird",
        "Rebirth",
        "Tempest Efreet",
    }
)

RESTRICTED_CARDS: frozenset[str] = frozenset(
    {
        "Ancestral Recall",
        "Balance",
        "Black Lotus",
        "Braingeyser",
        "Channel",
        "Chaos Orb",
        "Contract from Below",
        "Darkpact",
        "Demonic Tutor",
        "Library of Alexandria",
        "Mana Drain",
        "Mind Twist",
        "Mishra's Workshop",
        "Mox Emerald",
        "Mox Jet",
        "Mox Pearl",
        "Mox Ruby",
        "Mox Sapphire",
        "Regrowth",
        "Sol Ring",
        "Strip Mine",
        "Tempest Efreet",
        "Time Walk",
        "Timetwister",
        "Wheel of Fortune",
    }
)

_BANNED_FOLD = frozenset(name.casefold() for name in BANNED_CARDS)
_RESTRICTED_FOLD = frozenset(name.casefold() for name in RESTRICTED_CARDS)


def is_banned(card_name: str) -> bool:
    return card_name.casefold() in _BANNED_FOLD


def is_restricted(card_name: str) -> bool:
    return card_name.casefold() in _RESTRICTED_FOLD


def old_school_swedish_scryfall_clause() -> str:
    """Scryfall query fragment limiting results to Swedish OS legal sets."""
    sets = " OR ".join(f"e:{code}" for code in LEGAL_SET_CODES)
    return f"({sets})"


def old_school_swedish_prompt_notes() -> str:
    banned = ", ".join(sorted(BANNED_CARDS))
    restricted = ", ".join(sorted(RESTRICTED_CARDS))
    sets = ", ".join(LEGAL_SET_NAMES)
    return (
        "Format details: Old School Swedish (Swedish OS / 93/94).\n"
        f"Legal sets: {sets}.\n"
        "Ante cards are banned unless the tournament/game is played for ante.\n"
        f"Banned (do not recommend): {banned}.\n"
        f"Restricted (recommend at most one copy): {restricted}.\n"
        "Do not claim tournament legality; B&R lists can change. "
        "Rules reference: https://ragingbullseries.com/index.php/swedish-os-rules/"
    )
