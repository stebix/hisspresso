"""Terminal graph rendering via plotext."""

from __future__ import annotations

import io
import sys
from datetime import UTC, datetime, timedelta
from typing import cast

from hisspresso.graph_theme import DEFAULT_THEME, GraphTheme
from hisspresso.model import caffeine_curve


def render(
    doses: list[dict[str, object]],
    half_life_hours: float = 5.0,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    hours: int | None = None,
    theme: GraphTheme = DEFAULT_THEME,
) -> None:
    """Draw a residual-caffeine graph to the terminal.

    The display window is determined by *start*/*end* if given, otherwise by
    *hours* (last N hours ending at now), otherwise by the auto-heuristic.
    """
    import plotext as plt

    from hisspresso.model import auto_window

    # Ensure stdout can handle Unicode characters used by plotext on Windows.
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    now = datetime.now(UTC)

    if start is not None or end is not None:
        # Explicit boundaries — fill in whichever side is missing.
        if start is None:
            start = (end or now) - timedelta(hours=24)
        if end is None:
            end = now
    elif hours is not None:
        start = now - timedelta(hours=hours)
        end = now
    else:
        start, end = auto_window(doses, half_life_hours)

    curve = caffeine_curve(doses, start, end, half_life_hours, steps=200)

    date_fmt = "%d/%m/%Y %H:%M"
    plotext_fmt = "d/m/Y H:M"

    # Convert to local time for display.
    times = [t.astimezone().strftime(date_fmt) for t, _ in curve]
    values = [v for _, v in curve]

    plt.clear_figure()
    plt.date_form(plotext_fmt)
    plt.plot(
        times,
        values,
        label="caffeine (mg)",
        marker=theme.curve_marker,
        color=theme.curve_color,
    )

    # Threshold reference lines.
    plt.hline(50, color=theme.threshold_low_color)
    plt.hline(200, color=theme.threshold_high_color)

    # Dose markers.
    for dose in doses:
        ts = _parse_ts(dose["timestamp"])
        if ts < start or ts > end:
            continue
        local_str = ts.astimezone().strftime(date_fmt)
        count = cast(int, dose.get("count", 1))
        bev = dose.get("beverage", "?")
        label = f"{count}× {bev}" if count > 1 else str(bev)
        plt.vline(local_str, color=theme.dose_marker_color)
        plt.text(
            label,
            x=local_str,
            y=cast(float, dose["caffeine_mg"]) * count,
            color=theme.dose_marker_color,
        )

    # "Now" marker.
    now_str = now.astimezone().strftime(date_fmt)
    plt.vline(now_str, color=theme.now_marker_color)
    plt.text("now", x=now_str, y=0, color=theme.now_marker_color)

    plt.title("Residual Caffeine")
    plt.xlabel("Time")
    plt.ylabel("mg")

    # Apply plotext canvas theme from our GraphTheme.
    plt.canvas_color(theme.canvas_color)
    plt.axes_color(theme.axes_color)
    plt.ticks_color(theme.ticks_color)
    # plotext's public ticks_style() rejects "default" (internal-only value),
    # so pass None to get the same no-op behavior.
    ticks_style = None if theme.ticks_style == "default" else theme.ticks_style
    plt.ticks_style(ticks_style)

    plt.show()


def _parse_ts(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))
