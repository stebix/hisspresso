"""Graph theme: dataclass definition, TOML loading, and discovery."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from importlib import resources
from pathlib import Path


@dataclass(frozen=True)
class GraphTheme:
    """Visual settings applied to the plotext caffeine graph."""

    # plotext canvas / chrome
    canvas_color: str
    axes_color: str
    ticks_color: str
    ticks_style: str

    # main curve
    curve_color: str
    curve_marker: str

    # hisspresso element colors
    threshold_low_color: str
    threshold_high_color: str
    dose_marker_color: str
    now_marker_color: str


DEFAULT_THEME = GraphTheme(
    canvas_color="black",
    axes_color="black",
    ticks_color="orange",
    ticks_style="default",
    curve_color="blue",
    curve_marker="braille",
    threshold_low_color="green",
    threshold_high_color="red",
    dose_marker_color="blue",
    now_marker_color="yellow",
)


def _bundled_themes_dir() -> Path:
    """Return the path to the bundled themes directory inside the package."""
    return Path(str(resources.files("hisspresso") / "themes"))


def _parse_toml(data: dict[str, object]) -> GraphTheme:
    """Build a *GraphTheme* from parsed TOML data."""
    canvas = data.get("canvas", {})
    curve = data.get("curve", {})
    elements = data.get("elements", {})

    if not isinstance(canvas, dict) or not isinstance(curve, dict):
        raise ValueError("Theme TOML must contain [canvas] and [curve] sections.")
    if not isinstance(elements, dict):
        raise ValueError("Theme TOML must contain an [elements] section.")

    return GraphTheme(
        canvas_color=str(canvas.get("background", DEFAULT_THEME.canvas_color)),
        axes_color=str(canvas.get("axes", DEFAULT_THEME.axes_color)),
        ticks_color=str(canvas.get("ticks", DEFAULT_THEME.ticks_color)),
        ticks_style=str(canvas.get("ticks_style", DEFAULT_THEME.ticks_style)),
        curve_color=str(curve.get("color", DEFAULT_THEME.curve_color)),
        curve_marker=str(curve.get("marker", DEFAULT_THEME.curve_marker)),
        threshold_low_color=str(elements.get("threshold_low", DEFAULT_THEME.threshold_low_color)),
        threshold_high_color=str(
            elements.get("threshold_high", DEFAULT_THEME.threshold_high_color)
        ),
        dose_marker_color=str(elements.get("dose_marker", DEFAULT_THEME.dose_marker_color)),
        now_marker_color=str(elements.get("now_marker", DEFAULT_THEME.now_marker_color)),
    )


def load_graph_theme(name: str, data_dir: Path | None = None) -> GraphTheme:
    """Load a graph theme by *name*.

    Resolution order:
    1. ``<data_dir>/themes/<name>.toml``  (user override)
    2. Bundled ``hisspresso/themes/<name>.toml``

    Raises ``FileNotFoundError`` if no matching file is found.
    """
    # 1. User themes directory.
    if data_dir is not None:
        user_path = data_dir / "themes" / f"{name}.toml"
        if user_path.is_file():
            with open(user_path, "rb") as f:
                return _parse_toml(tomllib.load(f))

    # 2. Bundled themes.
    bundled_path = _bundled_themes_dir() / f"{name}.toml"
    if bundled_path.is_file():
        with open(bundled_path, "rb") as f:
            return _parse_toml(tomllib.load(f))

    available = ", ".join(sorted(list_graph_themes(data_dir)))
    msg = f"Unknown graph theme '{name}'. Available: {available}"
    raise FileNotFoundError(msg)


def list_graph_themes(data_dir: Path | None = None) -> list[str]:
    """Return sorted, deduplicated list of available theme names."""
    names: set[str] = set()

    bundled = _bundled_themes_dir()
    if bundled.is_dir():
        names.update(p.stem for p in bundled.glob("*.toml"))

    if data_dir is not None:
        user_dir = data_dir / "themes"
        if user_dir.is_dir():
            names.update(p.stem for p in user_dir.glob("*.toml"))

    return sorted(names)
