"""Tests for beverages.py — Phase 2."""

from __future__ import annotations

from hisspresso.beverages import list_all, lookup

# ── built-in lookup ──────────────────────────────────────────────────


def test_lookup_by_key() -> None:
    result = lookup("coffee")
    assert result is not None
    assert result.key == "coffee"
    assert result.caffeine_mg == 95
    assert result.custom is False


def test_lookup_by_alias() -> None:
    result = lookup("shot")
    assert result is not None
    assert result.key == "espresso"
    assert result.caffeine_mg == 63


def test_lookup_by_multi_word_alias() -> None:
    result = lookup("cold brew")
    assert result is not None
    assert result.key == "cold-brew"
    assert result.caffeine_mg == 155


def test_lookup_case_insensitive() -> None:
    result = lookup("MATCHA")
    assert result is not None
    assert result.key == "matcha"


def test_lookup_unknown_returns_none() -> None:
    assert lookup("unicorn-juice") is None


# ── custom beverage override ─────────────────────────────────────────


def test_custom_overrides_builtin() -> None:
    custom = [{"key": "coffee", "caffeine_mg": 120, "aliases": ""}]
    result = lookup("coffee", custom_beverages=custom)
    assert result is not None
    assert result.caffeine_mg == 120
    assert result.custom is True


def test_custom_lookup_by_alias() -> None:
    custom = [{"key": "oat-latte", "caffeine_mg": 63, "aliases": "oat latte,oatlatte"}]
    result = lookup("oat latte", custom_beverages=custom)
    assert result is not None
    assert result.key == "oat-latte"
    assert result.custom is True


def test_custom_falls_through_to_builtin() -> None:
    custom = [{"key": "oat-latte", "caffeine_mg": 63, "aliases": ""}]
    result = lookup("espresso", custom_beverages=custom)
    assert result is not None
    assert result.key == "espresso"
    assert result.custom is False


# ── list_all ─────────────────────────────────────────────────────────


def test_list_all_without_custom() -> None:
    items = list_all()
    keys = [i["key"] for i in items]
    assert "coffee" in keys
    assert "espresso" in keys
    assert all(i["custom"] is False for i in items)


def test_list_all_custom_shadows_builtin() -> None:
    custom = [{"key": "coffee", "caffeine_mg": 120, "aliases": ""}]
    items = list_all(custom_beverages=custom)
    coffee_items = [i for i in items if i["key"] == "coffee"]
    assert len(coffee_items) == 1
    assert coffee_items[0]["custom"] is True
    assert coffee_items[0]["caffeine_mg"] == 120


def test_list_all_custom_added_alongside_builtins() -> None:
    custom = [{"key": "oat-latte", "caffeine_mg": 63, "aliases": ""}]
    items = list_all(custom_beverages=custom)
    keys = [i["key"] for i in items]
    assert "oat-latte" in keys
    assert "coffee" in keys  # Built-in still present.
