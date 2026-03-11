"""Built-in beverage database and lookup logic."""

from __future__ import annotations

from dataclasses import dataclass

_BUILTINS: list[dict[str, object]] = [
    {"key": "espresso", "aliases": ["shot"], "caffeine_mg": 63},
    {"key": "coffee", "aliases": ["drip", "filter"], "caffeine_mg": 95},
    {"key": "americano", "aliases": [], "caffeine_mg": 95},
    {"key": "latte", "aliases": [], "caffeine_mg": 63},
    {"key": "cold-brew", "aliases": ["cold brew", "coldbrew"], "caffeine_mg": 155},
    {"key": "green-tea", "aliases": ["green tea"], "caffeine_mg": 30},
    {"key": "black-tea", "aliases": ["black tea"], "caffeine_mg": 50},
    {"key": "matcha", "aliases": [], "caffeine_mg": 70},
    {"key": "red-bull", "aliases": ["red bull", "redbull"], "caffeine_mg": 80},
    {"key": "monster", "aliases": [], "caffeine_mg": 160},
]


@dataclass(frozen=True)
class BeverageMatch:
    """Result of a beverage lookup."""

    key: str
    caffeine_mg: float
    custom: bool


def _normalize(name: str) -> str:
    return name.strip().lower()


def lookup(
    name: str,
    custom_beverages: list[dict[str, object]] | None = None,
) -> BeverageMatch | None:
    """Look up a beverage by key or alias. Custom beverages are checked first."""
    query = _normalize(name)

    # Check user-defined custom beverages first.
    if custom_beverages:
        for bev in custom_beverages:
            key = str(bev["key"]).lower()
            if query == key:
                return BeverageMatch(
                    key=str(bev["key"]),
                    caffeine_mg=float(bev["caffeine_mg"]),  # type: ignore[arg-type]
                    custom=True,
                )
            aliases_raw = bev.get("aliases", "")
            if isinstance(aliases_raw, str) and aliases_raw:
                aliases = [a.strip().lower() for a in aliases_raw.split(",")]
            else:
                aliases = []
            if query in aliases:
                return BeverageMatch(
                    key=str(bev["key"]),
                    caffeine_mg=float(bev["caffeine_mg"]),  # type: ignore[arg-type]
                    custom=True,
                )

    # Check built-ins.
    for bev in _BUILTINS:
        key = str(bev["key"]).lower()
        aliases = [a.lower() for a in bev["aliases"]]  # type: ignore[union-attr]
        if query == key or query in aliases:
            return BeverageMatch(
                key=str(bev["key"]),
                caffeine_mg=float(bev["caffeine_mg"]),  # type: ignore[arg-type]
                custom=False,
            )

    return None


def list_all(
    custom_beverages: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    """Return a merged list of all beverages (custom + built-in), custom first.

    Each entry: {key, caffeine_mg, aliases, custom}.
    Custom entries that shadow a built-in replace it; they don't duplicate.
    """
    result: list[dict[str, object]] = []
    seen_keys: set[str] = set()

    # Custom beverages first.
    if custom_beverages:
        for bev in custom_beverages:
            key = str(bev["key"]).lower()
            aliases_raw = bev.get("aliases", "")
            aliases = aliases_raw if isinstance(aliases_raw, str) else ""
            result.append(
                {
                    "key": bev["key"],
                    "caffeine_mg": bev["caffeine_mg"],
                    "aliases": aliases,
                    "custom": True,
                }
            )
            seen_keys.add(key)

    # Built-ins (skip if shadowed by custom).
    for bev in _BUILTINS:
        key = str(bev["key"]).lower()
        if key in seen_keys:
            continue
        result.append(
            {
                "key": bev["key"],
                "caffeine_mg": bev["caffeine_mg"],
                "aliases": ", ".join(bev["aliases"]),  # type: ignore[arg-type]
                "custom": False,
            }
        )

    return result
