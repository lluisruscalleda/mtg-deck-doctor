"""Async Scryfall API client."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.exceptions import CardResolutionError
from app.core.logging import get_logger
from app.formats.old_school_swedish import (
    is_banned,
    old_school_swedish_scryfall_clause,
)

logger = get_logger(__name__)


class ResolvedCard:
    """Normalized card metadata used by metrics and the agent."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.raw = data
        self.id: str = str(data.get("id", ""))
        self.name: str = str(data.get("name", ""))
        self.mana_cost: str | None = data.get("mana_cost")
        self.cmc: float | None = _as_float(data.get("cmc"))
        self.type_line: str = str(data.get("type_line") or "")
        self.oracle_text: str | None = data.get("oracle_text")
        self.colors: list[str] = list(data.get("colors") or [])
        self.color_identity: list[str] = list(data.get("color_identity") or [])
        prices = data.get("prices") or {}
        self.price_usd: float | None = _as_float(prices.get("usd"))
        self.layout: str = str(data.get("layout") or "")
        self.card_faces: list[dict[str, Any]] = list(data.get("card_faces") or [])

    @property
    def is_land(self) -> bool:
        return "Land" in self.type_line

    @property
    def primary_type(self) -> str:
        type_line = self.type_line
        if "—" in type_line:
            type_line = type_line.split("—", 1)[0]
        tokens = type_line.replace("//", " ").split()
        broad_types = (
            "Creature",
            "Instant",
            "Sorcery",
            "Artifact",
            "Enchantment",
            "Planeswalker",
            "Land",
            "Battle",
        )
        for token in broad_types:
            if token in tokens:
                return token
        return "Other"

    def mana_value_for_metrics(self) -> float | None:
        """
        Mana-value policy for multi-face cards:
        - Prefer top-level `cmc` when present (Scryfall aggregates it).
        - Otherwise use the first face with a numeric cmc/mana_cost.
        - Lands without a meaningful CMC return None (excluded from average MV).
        """
        if self.cmc is not None:
            if self.is_land and self.cmc == 0:
                return None
            return self.cmc
        for face in self.card_faces:
            face_cmc = _as_float(face.get("cmc"))
            if face_cmc is not None:
                return face_cmc
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "mana_cost": self.mana_cost,
            "cmc": self.cmc,
            "type_line": self.type_line,
            "oracle_text": self.oracle_text,
            "colors": self.colors,
            "color_identity": self.color_identity,
            "price_usd": self.price_usd,
            "layout": self.layout,
            "is_land": self.is_land,
            "primary_type": self.primary_type,
            "mana_value": self.mana_value_for_metrics(),
        }


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class ScryfallClient:
    """Thin async client with per-instance cache and basic rate-limit handling."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = client
        self._owns_client = client is None
        self._cache: dict[str, ResolvedCard | None] = {}
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> ScryfallClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.settings.scryfall_base_url.rstrip("/"),
                headers={
                    "User-Agent": self.settings.scryfall_user_agent,
                    "Accept": "application/json",
                },
                timeout=httpx.Timeout(20.0),
            )
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("ScryfallClient must be used as an async context manager")
        return self._client

    async def resolve_card_name(self, name: str) -> ResolvedCard:
        key = name.casefold().strip()
        async with self._lock:
            if key in self._cache:
                cached = self._cache[key]
                if cached is None:
                    raise CardResolutionError(f"Unknown card: {name}")
                return cached

        card = await self._fetch_named(name)
        async with self._lock:
            self._cache[key] = card
        return card

    async def resolve_many(
        self,
        names: list[str],
    ) -> tuple[dict[str, ResolvedCard], list[str], list[str]]:
        """
        Resolve unique card names.

        Returns (resolved_by_input_name, unresolved_names, warnings).
        """
        resolved: dict[str, ResolvedCard] = {}
        unresolved: list[str] = []
        warnings: list[str] = []

        unique: list[str] = []
        seen: set[str] = set()
        for name in names:
            key = name.casefold()
            if key not in seen:
                seen.add(key)
                unique.append(name)

        for name in unique:
            try:
                card = await self.resolve_card_name(name)
                resolved[name] = card
                # Gentle pacing to respect Scryfall guidelines (~10 req/s).
                await asyncio.sleep(0.05)
            except CardResolutionError:
                unresolved.append(name)
                warnings.append(f"Could not resolve card name against Scryfall: {name}")
            except httpx.HTTPError as exc:
                logger.warning("Scryfall HTTP error for %s: %s", name, type(exc).__name__)
                unresolved.append(name)
                warnings.append(f"Temporary Scryfall error while resolving: {name}")

        return resolved, unresolved, warnings

    async def search_candidates(
        self,
        *,
        colors: list[str],
        format_name: str = "old_school_swedish",
        query_extra: str = "",
        limit: int = 20,
    ) -> list[ResolvedCard]:
        """Fetch a bounded set of candidate cards for recommendations."""
        color_clause = ""
        if colors:
            color_clause = "c:" + "".join(sorted(set(colors))).lower()

        format_key = format_name.casefold().strip()
        order = "name"
        if format_key == "old_school_swedish":
            format_clause = old_school_swedish_scryfall_clause()
        elif format_key == "custom":
            format_clause = ""
        elif format_key == "commander":
            format_clause = "f:commander"
            order = "edhrec"
        else:
            # Scryfall format filters use the same identifiers for constructed formats.
            format_clause = f"f:{format_key}"

        parts = (color_clause, format_clause, "-t:land", query_extra)
        query = " ".join(part for part in parts if part)
        params = {"q": query, "unique": "cards", "order": order}
        data = await self._request_json("GET", "/cards/search", params=params)
        cards = [ResolvedCard(item) for item in data.get("data", [])]
        if format_key == "old_school_swedish":
            cards = [card for card in cards if not is_banned(card.name)]
        return cards[:limit]

    async def _fetch_named(self, name: str) -> ResolvedCard:
        try:
            data = await self._request_json(
                "GET",
                "/cards/named",
                params={"exact": name},
            )
            return ResolvedCard(data)
        except CardResolutionError:
            # Fall back to fuzzy only when exact fails with 404.
            data = await self._request_json(
                "GET",
                "/cards/named",
                params={"fuzzy": name},
            )
            return ResolvedCard(data)

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        retries: int = 3,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(retries):
            try:
                response = await self.client.request(method, path, params=params)
                if response.status_code == 404:
                    raise CardResolutionError(f"Unknown card for path {path}")
                if response.status_code == 429:
                    retry_after = float(response.headers.get("Retry-After", "0.5"))
                    await asyncio.sleep(retry_after)
                    continue
                if response.status_code >= 500:
                    await asyncio.sleep(0.25 * (attempt + 1))
                    continue
                response.raise_for_status()
                return response.json()
            except CardResolutionError:
                raise
            except httpx.HTTPError as exc:
                last_error = exc
                await asyncio.sleep(0.25 * (attempt + 1))
        raise httpx.HTTPError(f"Scryfall request failed after retries: {last_error}")
