"""Tests for model.py — Phase 4."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from hisspresso.model import auto_window, caffeine_curve, residual_caffeine, time_to_threshold


def _utc(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 3, 10, hour, minute, tzinfo=UTC)


def _dose(ts: datetime, mg: float = 95.0, count: int = 1) -> dict[str, object]:
    return {
        "timestamp": ts.isoformat(),
        "caffeine_mg": mg,
        "count": count,
    }


# ── residual_caffeine ────────────────────────────────────────────────


def test_single_dose_at_dose_time() -> None:
    dose = _dose(_utc(8), mg=100)
    result = residual_caffeine([dose], at=_utc(8), half_life_hours=5)
    assert result == 100.0


def test_single_dose_one_half_life_later() -> None:
    dose = _dose(_utc(8), mg=100)
    result = residual_caffeine([dose], at=_utc(13), half_life_hours=5)
    assert abs(result - 50.0) < 0.01


def test_single_dose_two_half_lives_later() -> None:
    dose = _dose(_utc(8), mg=100)
    result = residual_caffeine([dose], at=_utc(18), half_life_hours=5)
    assert abs(result - 25.0) < 0.01


def test_multiple_doses_sum() -> None:
    doses = [
        _dose(_utc(8), mg=100),
        _dose(_utc(10), mg=100),
    ]
    # At t=13 (5h after first, 3h after second):
    # first: 100 * 0.5^(5/5) = 50
    # second: 100 * 0.5^(3/5) ≈ 65.975
    result = residual_caffeine(doses, at=_utc(13), half_life_hours=5)
    assert abs(result - (50 + 100 * 0.5 ** (3 / 5))) < 0.01


def test_count_multiplier() -> None:
    dose = _dose(_utc(8), mg=63, count=2)
    result = residual_caffeine([dose], at=_utc(8), half_life_hours=5)
    assert result == 126.0


def test_future_dose_ignored() -> None:
    dose = _dose(_utc(14), mg=100)
    result = residual_caffeine([dose], at=_utc(8), half_life_hours=5)
    assert result == 0.0


def test_empty_doses() -> None:
    assert residual_caffeine([], at=_utc(8)) == 0.0


# ── caffeine_curve ───────────────────────────────────────────────────


def test_curve_returns_correct_length() -> None:
    dose = _dose(_utc(8), mg=100)
    curve = caffeine_curve([dose], start=_utc(6), end=_utc(18), steps=12)
    assert len(curve) == 13  # steps + 1


def test_curve_monotonically_decays_after_last_dose() -> None:
    dose = _dose(_utc(8), mg=100)
    curve = caffeine_curve([dose], start=_utc(8), end=_utc(20), steps=50)
    values = [v for _, v in curve]
    for i in range(1, len(values)):
        assert values[i] <= values[i - 1]


def test_curve_filters_ancient_doses() -> None:
    ancient = _dose(_utc(8) - timedelta(hours=100), mg=100)
    recent = _dose(_utc(8), mg=100)
    # With default 5h half-life, window is 25h. The ancient dose is 100h old → filtered out.
    curve = caffeine_curve(
        [ancient, recent], start=_utc(8), end=_utc(20), half_life_hours=5, steps=10
    )
    # At start, should be ~100 mg (only recent dose contributes meaningfully).
    assert abs(curve[0][1] - 100.0) < 0.01


# ── auto_window ─────────────────────────────────────────────────────


def test_auto_window_covers_recent_dose() -> None:
    """Window should start before the earliest dose that still has residual >= 1 mg."""
    now = _utc(20)
    dose = _dose(_utc(12), mg=100)  # 8h ago → residual ~100*0.5^(8/5) ≈ 33 mg

    start, end = auto_window([dose], half_life_hours=5.0, _now=now)

    assert end == now
    # Start should be ~1h before the dose (padding).
    assert start <= _utc(11)
    # Window should be at least 4h (min_hours).
    assert (end - start).total_seconds() / 3600 >= 4.0


def test_auto_window_no_relevant_doses() -> None:
    """When no doses have residual >= 1 mg, fall back to 24h window."""
    now = _utc(12)
    # Dose 100h ago — residual is basically zero.
    ancient = _dose(_utc(12) - timedelta(hours=100), mg=100)

    start, end = auto_window([ancient], half_life_hours=5.0, _now=now)

    assert end == now
    expected_hours = (end - start).total_seconds() / 3600
    assert abs(expected_hours - 24.0) < 0.01


def test_auto_window_respects_min_hours() -> None:
    """A dose logged moments ago should still produce at least min_hours window."""
    now = _utc(12)
    dose = _dose(_utc(12), mg=100)  # logged at "now"

    start, end = auto_window([dose], half_life_hours=5.0, min_hours=4.0, _now=now)

    window_hours = (end - start).total_seconds() / 3600
    assert window_hours >= 4.0


def test_auto_window_respects_max_hours() -> None:
    """Window should not exceed max_hours even with ancient relevant doses."""
    now = _utc(12)
    # Giant dose 40h ago — may still have >1 mg residual.
    big = _dose(_utc(12) - timedelta(hours=40), mg=10_000)

    start, end = auto_window([big], half_life_hours=5.0, max_hours=48.0, _now=now)

    window_hours = (end - start).total_seconds() / 3600
    assert window_hours <= 48.0


# ── time_to_threshold ───────────────────────────────────────────────


def test_time_to_threshold_single_dose() -> None:
    """100 mg at t=8 with half-life 5h reaches 10 mg after log2(10) * 5 ≈ 16.61h."""
    import math

    now = _utc(8)
    dose = _dose(_utc(8), mg=100)
    expected_hours = 5.0 * math.log2(100 / 10)  # ≈ 16.61h

    result = time_to_threshold([dose], threshold_mg=10.0, half_life_hours=5.0, _now=now)

    assert result is not None
    actual_hours = (result - now).total_seconds() / 3600
    assert abs(actual_hours - expected_hours) < 0.02  # within ~1 minute


def test_time_to_threshold_already_below() -> None:
    """If current level is already below threshold, returns None."""
    now = _utc(20)
    # 100 mg at t=8, now t=20 → 12h elapsed → 100 * 0.5^(12/5) ≈ 18.9 mg
    dose = _dose(_utc(8), mg=100)

    result = time_to_threshold([dose], threshold_mg=20.0, half_life_hours=5.0, _now=now)

    assert result is None


def test_time_to_threshold_multiple_doses() -> None:
    """With multiple doses, threshold crossing is later than any single dose alone."""
    import math

    now = _utc(10)
    doses = [
        _dose(_utc(8), mg=100),
        _dose(_utc(10), mg=100),
    ]

    result = time_to_threshold(doses, threshold_mg=10.0, half_life_hours=5.0, _now=now)
    assert result is not None

    # Must be later than a single 100 mg dose at t=10 would clear.
    single_clear_hours = 5.0 * math.log2(100 / 10)
    single_clear_time = now + timedelta(hours=single_clear_hours)
    assert result > single_clear_time

    # Verify the residual is actually around the threshold at that time.
    level = residual_caffeine(doses, at=result, half_life_hours=5.0)
    assert abs(level - 10.0) < 0.1


def test_time_to_threshold_empty_doses() -> None:
    """No doses → residual is 0 → already below any positive threshold."""
    result = time_to_threshold([], threshold_mg=10.0, half_life_hours=5.0, _now=_utc(12))
    assert result is None


def test_time_to_threshold_count_multiplier() -> None:
    """Count=2 means more caffeine, so it takes longer to clear."""
    now = _utc(8)
    single = _dose(_utc(8), mg=63, count=1)
    double = _dose(_utc(8), mg=63, count=2)

    t_single = time_to_threshold([single], threshold_mg=10.0, half_life_hours=5.0, _now=now)
    t_double = time_to_threshold([double], threshold_mg=10.0, half_life_hours=5.0, _now=now)

    assert t_single is not None
    assert t_double is not None
    assert t_double > t_single
