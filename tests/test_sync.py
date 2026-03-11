"""Tests for sync.py — Phase 7."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from hisspresso.storage import Store
from hisspresso.sync import pull, push


@pytest.fixture()
def sync_dir(tmp_path: Path) -> Path:
    d = tmp_path / "sync"
    d.mkdir()
    return d


@pytest.fixture()
def store_a(tmp_path: Path) -> Store:
    return Store(tmp_path / "a.db", machine_id="machine-aaa")


@pytest.fixture()
def store_b(tmp_path: Path) -> Store:
    return Store(tmp_path / "b.db", machine_id="machine-bbb")


# ── push / pull round-trip ───────────────────────────────────────────


def test_push_then_pull(store_a: Store, store_b: Store, sync_dir: Path) -> None:
    # Machine A logs a dose.
    store_a.add_dose(
        timestamp="2026-03-10T09:00:00+00:00",
        beverage="coffee",
        caffeine_mg=95,
    )

    # A pushes.
    count = push(store_a, sync_dir, "machine-aaa")
    assert count == 1
    assert (sync_dir / "machine-aaa.jsonl").exists()

    # B pulls.
    inserted, updated = pull(store_b, sync_dir, "machine-bbb")
    assert inserted == 1
    assert updated == 0

    # B should now have the dose.
    doses = store_b.get_active_doses(since="2026-03-10T00:00:00+00:00")
    assert len(doses) == 1
    assert doses[0]["beverage"] == "coffee"


def test_push_nothing_new(store_a: Store, sync_dir: Path) -> None:
    count = push(store_a, sync_dir, "machine-aaa")
    assert count == 0


def test_pull_empty_sync_dir(store_b: Store, sync_dir: Path) -> None:
    inserted, updated = pull(store_b, sync_dir, "machine-bbb")
    assert inserted == 0
    assert updated == 0


def test_pull_skips_own_feed(store_a: Store, sync_dir: Path) -> None:
    store_a.add_dose(
        timestamp="2026-03-10T09:00:00+00:00",
        beverage="coffee",
        caffeine_mg=95,
    )
    push(store_a, sync_dir, "machine-aaa")

    # Pull on the same machine — should skip its own file.
    inserted, updated = pull(store_a, sync_dir, "machine-aaa")
    assert inserted == 0
    assert updated == 0


# ── incremental sync ─────────────────────────────────────────────────


def test_incremental_pull(store_a: Store, store_b: Store, sync_dir: Path) -> None:
    # First dose + push + pull.
    store_a.add_dose(timestamp="2026-03-10T08:00:00+00:00", beverage="a", caffeine_mg=10)
    push(store_a, sync_dir, "machine-aaa")
    pull(store_b, sync_dir, "machine-bbb")

    # Second dose + push + pull.
    time.sleep(0.01)
    store_a.add_dose(timestamp="2026-03-10T09:00:00+00:00", beverage="b", caffeine_mg=20)
    push(store_a, sync_dir, "machine-aaa")
    inserted, updated = pull(store_b, sync_dir, "machine-bbb")

    # Only the second dose should be newly inserted.
    assert inserted == 1
    assert updated == 0

    doses = store_b.get_active_doses(since="2026-03-10T00:00:00+00:00")
    assert len(doses) == 2


# ── sync soft-delete ─────────────────────────────────────────────────


def test_sync_soft_delete(store_a: Store, store_b: Store, sync_dir: Path) -> None:
    # A logs and pushes.
    dose_id = store_a.add_dose(
        timestamp="2026-03-10T09:00:00+00:00", beverage="coffee", caffeine_mg=95
    )
    push(store_a, sync_dir, "machine-aaa")
    pull(store_b, sync_dir, "machine-bbb")

    # B should have the dose.
    assert len(store_b.get_active_doses(since="2026-03-10T00:00:00+00:00")) == 1

    # A deletes and pushes again.
    time.sleep(0.01)
    store_a.soft_delete(dose_id[:8])
    push(store_a, sync_dir, "machine-aaa")

    # B pulls — should see the deletion.
    inserted, updated = pull(store_b, sync_dir, "machine-bbb")
    assert updated == 1
    assert store_b.get_active_doses(since="2026-03-10T00:00:00+00:00") == []


# ── beverage sync ────────────────────────────────────────────────────


def test_sync_custom_beverages(store_a: Store, store_b: Store, sync_dir: Path) -> None:
    store_a.add_beverage("oat-latte", 63, aliases="oat latte")
    push(store_a, sync_dir, "machine-aaa")
    pull(store_b, sync_dir, "machine-bbb")

    bevs = store_b.get_custom_beverages()
    assert len(bevs) == 1
    assert bevs[0]["key"] == "oat-latte"
