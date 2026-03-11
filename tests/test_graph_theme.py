"""Tests for graph_theme.py — theme loading and discovery."""

from __future__ import annotations

from pathlib import Path

import pytest

from hisspresso.graph_theme import (
    DEFAULT_THEME,
    GraphTheme,
    list_graph_themes,
    load_graph_theme,
)

# ── bundled themes ──────────────────────────────────────────────────


def test_load_bundled_dark() -> None:
    theme = load_graph_theme("dark")
    assert isinstance(theme, GraphTheme)
    assert theme.canvas_color == "black"


def test_load_bundled_light() -> None:
    theme = load_graph_theme("light")
    assert isinstance(theme, GraphTheme)
    assert theme.canvas_color == "white"


def test_list_includes_bundled() -> None:
    names = list_graph_themes()
    assert "dark" in names
    assert "light" in names


# ── user themes ─────────────────────────────────────────────────────


def test_load_user_theme(tmp_path: Path) -> None:
    themes_dir = tmp_path / "themes"
    themes_dir.mkdir()
    (themes_dir / "custom.toml").write_text(
        """\
[canvas]
background = "gray"
axes = "gray"
ticks = "white"
ticks_style = "bold"

[curve]
color = "red"
marker = "dot"

[elements]
threshold_low = "cyan"
threshold_high = "magenta"
dose_marker = "green"
now_marker = "orange"
""",
        encoding="utf-8",
    )
    theme = load_graph_theme("custom", data_dir=tmp_path)
    assert theme.canvas_color == "gray"
    assert theme.curve_color == "red"
    assert theme.curve_marker == "dot"
    assert theme.dose_marker_color == "green"


def test_user_theme_overrides_bundled(tmp_path: Path) -> None:
    """A user file named 'dark.toml' should take precedence over the bundled one."""
    themes_dir = tmp_path / "themes"
    themes_dir.mkdir()
    (themes_dir / "dark.toml").write_text(
        """\
[canvas]
background = "navy"
axes = "navy"
ticks = "white"
ticks_style = "bold"

[curve]
color = "cyan"
marker = "hd"

[elements]
threshold_low = "green"
threshold_high = "red"
dose_marker = "blue"
now_marker = "yellow"
""",
        encoding="utf-8",
    )
    theme = load_graph_theme("dark", data_dir=tmp_path)
    assert theme.canvas_color == "navy"
    assert theme.curve_marker == "hd"


def test_list_merges_user_and_bundled(tmp_path: Path) -> None:
    themes_dir = tmp_path / "themes"
    themes_dir.mkdir()
    (themes_dir / "solarized.toml").write_text(
        """\
[canvas]
background = "black"
[curve]
color = "blue"
[elements]
""",
        encoding="utf-8",
    )
    names = list_graph_themes(data_dir=tmp_path)
    assert "dark" in names
    assert "light" in names
    assert "solarized" in names


# ── error handling ──────────────────────────────────────────────────


def test_load_unknown_theme_raises() -> None:
    with pytest.raises(FileNotFoundError, match="Unknown graph theme"):
        load_graph_theme("nonexistent")


def test_load_unknown_lists_available() -> None:
    with pytest.raises(FileNotFoundError, match="dark"):
        load_graph_theme("nonexistent")


# ── defaults / partial TOML ─────────────────────────────────────────


def test_partial_toml_uses_defaults(tmp_path: Path) -> None:
    """Missing keys in the TOML should fall back to DEFAULT_THEME values."""
    themes_dir = tmp_path / "themes"
    themes_dir.mkdir()
    (themes_dir / "minimal.toml").write_text(
        """\
[canvas]
background = "gray"

[curve]

[elements]
""",
        encoding="utf-8",
    )
    theme = load_graph_theme("minimal", data_dir=tmp_path)
    assert theme.canvas_color == "gray"
    # Everything else should be default.
    assert theme.curve_color == DEFAULT_THEME.curve_color
    assert theme.ticks_color == DEFAULT_THEME.ticks_color
    assert theme.now_marker_color == DEFAULT_THEME.now_marker_color


# ── frozen dataclass ────────────────────────────────────────────────


def test_theme_is_frozen() -> None:
    theme = load_graph_theme("dark")
    with pytest.raises(AttributeError):
        theme.canvas_color = "red"  # type: ignore[misc]
