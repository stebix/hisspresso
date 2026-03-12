"""Caffeine pharmacokinetics — first-order exponential decay."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import cast


def residual_caffeine(
    doses: list[dict[str, object]],
    at: datetime,
    half_life_hours: float = 5.0,
) -> float:
    """Total residual caffeine (mg) at time *at* from all *doses*.

    Each dose dict must have: timestamp (ISO str or datetime), caffeine_mg, count.
    """
    total = 0.0
    for dose in doses:
        t_dose = _parse_ts(dose["timestamp"])
        elapsed_hours = (at - t_dose).total_seconds() / 3600
        if elapsed_hours < 0:
            continue  # Dose is in the future — skip.
        mg = cast(float, dose["caffeine_mg"]) * cast(int, dose["count"])
        total += mg * (0.5 ** (elapsed_hours / half_life_hours))
    return total


def caffeine_curve(
    doses: list[dict[str, object]],
    start: datetime,
    end: datetime,
    half_life_hours: float = 5.0,
    steps: int = 200,
) -> list[tuple[datetime, float]]:
    """Compute residual caffeine at *steps* evenly-spaced points from *start* to *end*.

    Only considers doses within ``start - 5 * half_life`` to avoid scanning ancient history.
    """
    window = timedelta(hours=5 * half_life_hours)
    relevant = [d for d in doses if _parse_ts(d["timestamp"]) >= start - window]

    delta = (end - start) / steps
    return [
        (t := start + delta * i, residual_caffeine(relevant, t, half_life_hours))
        for i in range(steps + 1)
    ]


def auto_window(
    doses: list[dict[str, object]],
    half_life_hours: float = 5.0,
    threshold_mg: float = 1.0,
    min_hours: float = 4.0,
    max_hours: float = 48.0,
    padding_hours: float = 1.0,
    *,
    _now: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Compute a display window that covers all doses with residual caffeine above *threshold_mg*.

    Returns ``(start, end)`` where *end* is always *now*.  If no doses are
    relevant the window falls back to 24 h.
    """
    from datetime import UTC

    now = _now or datetime.now(UTC)

    # For each dose, check if it still contributes above threshold at *now*.
    relevant_timestamps: list[datetime] = []
    for dose in doses:
        t_dose = _parse_ts(dose["timestamp"])
        elapsed_hours = (now - t_dose).total_seconds() / 3600
        if elapsed_hours < 0:
            continue
        mg = cast(float, dose["caffeine_mg"]) * cast(int, dose["count"])
        remaining = mg * (0.5 ** (elapsed_hours / half_life_hours))
        if remaining >= threshold_mg:
            relevant_timestamps.append(t_dose)

    if relevant_timestamps:
        earliest = min(relevant_timestamps)
        start = earliest - timedelta(hours=padding_hours)
    else:
        # No relevant doses — fall back to 24 h.
        start = now - timedelta(hours=24)

    # Clamp the window.
    window_hours = (now - start).total_seconds() / 3600
    if window_hours < min_hours:
        start = now - timedelta(hours=min_hours)
    elif window_hours > max_hours:
        start = now - timedelta(hours=max_hours)

    return start, now


def time_to_threshold(
    doses: list[dict[str, object]],
    threshold_mg: float = 10.0,
    half_life_hours: float = 5.0,
    *,
    _now: datetime | None = None,
) -> datetime | None:
    """Find the earliest time after *now* when total residual caffeine drops below *threshold_mg*.

    Returns ``None`` if the current level is already at or below the threshold.
    Uses bisection — the total residual is monotonically decreasing after the last dose.
    """
    import math
    from datetime import UTC

    now = _now or datetime.now(UTC)

    current = residual_caffeine(doses, at=now, half_life_hours=half_life_hours)
    if current <= threshold_mg:
        return None

    # Upper bound: even if all current caffeine decayed as a single lump,
    # it would reach threshold after  half_life * log2(current / threshold)  hours.
    hours_needed = half_life_hours * math.log2(current / threshold_mg)
    upper = now + timedelta(hours=hours_needed + 1.0)  # +1h safety margin

    # Bisection to sub-minute precision.
    lo = now
    hi = upper
    for _ in range(60):  # 2^-60 of the interval ≈ negligible
        mid = lo + (hi - lo) / 2
        if residual_caffeine(doses, at=mid, half_life_hours=half_life_hours) > threshold_mg:
            lo = mid
        else:
            hi = mid
    return hi


def _parse_ts(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))
