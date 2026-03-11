"""Tests for storage.py — Phase 1."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from hisspresso.storage import Store


@pytest.fixture()
def store(tmp_path: Path) -> Store:
    db_path = tmp_path / "test.db"
    return Store(db_path, machine_id="machine-aaa")


@pytest.fixture()
def config_path(tmp_path: Path) -> Path:
    return tmp_path / "config.json"


# ── schema bootstrap ─────────────────────────────────────────────────


def test_schema_created(store: Store) -> None:
    version = store.get_meta("schema_version")
    assert version == "1"


# ── add_dose / get_active_doses round-trip ───────────────────────────


def test_add_and_retrieve_dose(store: Store) -> None:
    dose_id = store.add_dose(
        timestamp="2026-03-10T09:00:00+00:00",
        beverage="coffee",
        caffeine_mg=95.0,
    )
    assert isinstance(dose_id, str) and len(dose_id) == 36  # UUID format

    doses = store.get_active_doses(since="2026-03-10T00:00:00+00:00")
    assert len(doses) == 1
    assert doses[0]["beverage"] == "coffee"
    assert doses[0]["caffeine_mg"] == 95.0
    assert doses[0]["count"] == 1
    assert doses[0]["deleted"] == 0


def test_add_dose_with_count(store: Store) -> None:
    store.add_dose(
        timestamp="2026-03-10T09:00:00+00:00",
        beverage="espresso",
        caffeine_mg=63.0,
        count=2,
    )
    doses = store.get_active_doses(since="2026-03-10T00:00:00+00:00")
    assert doses[0]["count"] == 2


def test_get_active_doses_filters_by_time(store: Store) -> None:
    store.add_dose(timestamp="2026-03-09T08:00:00+00:00", beverage="a", caffeine_mg=10)
    store.add_dose(timestamp="2026-03-10T08:00:00+00:00", beverage="b", caffeine_mg=20)
    doses = store.get_active_doses(since="2026-03-10T00:00:00+00:00")
    assert len(doses) == 1
    assert doses[0]["beverage"] == "b"


# ── soft_delete / restore ────────────────────────────────────────────


def test_soft_delete_and_restore(store: Store) -> None:
    dose_id = store.add_dose(
        timestamp="2026-03-10T09:00:00+00:00",
        beverage="coffee",
        caffeine_mg=95.0,
    )
    # Delete by prefix.
    prefix = dose_id[:8]
    deleted_id = store.soft_delete(prefix)
    assert deleted_id == dose_id

    # Should be excluded from active query.
    assert store.get_active_doses(since="2026-03-10T00:00:00+00:00") == []

    # Restore.
    restored_id = store.restore(prefix)
    assert restored_id == dose_id
    assert len(store.get_active_doses(since="2026-03-10T00:00:00+00:00")) == 1


def test_soft_delete_nonexistent_prefix(store: Store) -> None:
    assert store.soft_delete("no-such-id") is None


def test_restore_non_deleted_dose(store: Store) -> None:
    dose_id = store.add_dose(
        timestamp="2026-03-10T09:00:00+00:00",
        beverage="coffee",
        caffeine_mg=95.0,
    )
    # Not deleted — restore should return None.
    assert store.restore(dose_id[:8]) is None


# ── undo_last ────────────────────────────────────────────────────────


def test_undo_last(store: Store) -> None:
    store.add_dose(timestamp="2026-03-10T08:00:00+00:00", beverage="a", caffeine_mg=10)
    time.sleep(0.01)  # Ensure distinct created_at.
    id_b = store.add_dose(timestamp="2026-03-10T09:00:00+00:00", beverage="b", caffeine_mg=20)
    undone = store.undo_last()
    assert undone == id_b

    doses = store.get_active_doses(since="2026-03-10T00:00:00+00:00")
    assert len(doses) == 1
    assert doses[0]["beverage"] == "a"


def test_undo_last_scoped_to_machine(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    store_a = Store(db_path, machine_id="machine-aaa")
    store_b = Store(db_path, machine_id="machine-bbb")

    store_a.add_dose(timestamp="2026-03-10T08:00:00+00:00", beverage="a", caffeine_mg=10)
    time.sleep(0.01)
    store_b.add_dose(timestamp="2026-03-10T09:00:00+00:00", beverage="b", caffeine_mg=20)

    # Undo from machine A should only affect A's dose.
    undone = store_a.undo_last()
    assert undone is not None
    doses = store_a.get_active_doses(since="2026-03-10T00:00:00+00:00")
    assert len(doses) == 1
    assert doses[0]["beverage"] == "b"


def test_undo_last_empty(store: Store) -> None:
    assert store.undo_last() is None


# ── resolve_id ───────────────────────────────────────────────────────


def test_resolve_id_unique_prefix(store: Store) -> None:
    dose_id = store.add_dose(
        timestamp="2026-03-10T09:00:00+00:00",
        beverage="coffee",
        caffeine_mg=95.0,
    )
    assert store.resolve_id(dose_id[:8]) == dose_id


def test_resolve_id_no_match(store: Store) -> None:
    assert store.resolve_id("zzz-no-match") is None


# ── list_doses ───────────────────────────────────────────────────────


def test_list_doses_excludes_deleted(store: Store) -> None:
    id1 = store.add_dose(timestamp="2026-03-10T08:00:00+00:00", beverage="a", caffeine_mg=10)
    store.add_dose(timestamp="2026-03-10T09:00:00+00:00", beverage="b", caffeine_mg=20)
    store.soft_delete(id1[:8])

    doses = store.list_doses()
    assert len(doses) == 1
    assert doses[0]["beverage"] == "b"


def test_list_doses_include_deleted(store: Store) -> None:
    id1 = store.add_dose(timestamp="2026-03-10T08:00:00+00:00", beverage="a", caffeine_mg=10)
    store.add_dose(timestamp="2026-03-10T09:00:00+00:00", beverage="b", caffeine_mg=20)
    store.soft_delete(id1[:8])

    doses = store.list_doses(include_deleted=True)
    assert len(doses) == 2


# ── purge ────────────────────────────────────────────────────────────


def test_purge_removes_old_deleted(store: Store) -> None:
    dose_id = store.add_dose(
        timestamp="2026-03-10T09:00:00+00:00", beverage="coffee", caffeine_mg=95
    )
    store.soft_delete(dose_id[:8])

    # Purge with 0-day threshold should remove the just-deleted row.
    removed = store.purge(older_than_days=0)
    assert removed == 1

    # Confirm it's gone even with include_deleted.
    assert store.list_doses(include_deleted=True) == []


def test_purge_keeps_recent_deleted(store: Store) -> None:
    dose_id = store.add_dose(
        timestamp="2026-03-10T09:00:00+00:00", beverage="coffee", caffeine_mg=95
    )
    store.soft_delete(dose_id[:8])

    # 30-day default should keep the just-deleted row.
    removed = store.purge(older_than_days=30)
    assert removed == 0


# ── custom beverages ─────────────────────────────────────────────────


def test_add_and_list_custom_beverages(store: Store) -> None:
    store.add_beverage("oat-latte", 63, aliases="oat latte,oatlatte")
    beverages = store.get_custom_beverages()
    assert len(beverages) == 1
    assert beverages[0]["key"] == "oat-latte"
    assert beverages[0]["caffeine_mg"] == 63
    assert "oat latte" in beverages[0]["aliases"]  # type: ignore[operator]


def test_remove_custom_beverage(store: Store) -> None:
    store.add_beverage("oat-latte", 63)
    assert store.remove_beverage("oat-latte") is True
    assert store.get_custom_beverages() == []


def test_remove_nonexistent_beverage(store: Store) -> None:
    assert store.remove_beverage("nope") is False


# ── sync merge ───────────────────────────────────────────────────────


def test_merge_remote_doses_insert(store: Store) -> None:
    remote_doses: list[dict[str, object]] = [
        {
            "id": "remote-uuid-1234",
            "machine_id": "machine-bbb",
            "timestamp": "2026-03-10T10:00:00+00:00",
            "beverage": "matcha",
            "caffeine_mg": 70.0,
            "count": 1,
            "deleted": 0,
            "created_at": "2026-03-10T10:00:00+00:00",
            "updated_at": "2026-03-10T10:00:00+00:00",
        }
    ]
    inserted, updated = store.merge_remote_doses(remote_doses)
    assert inserted == 1
    assert updated == 0

    doses = store.get_active_doses(since="2026-03-10T00:00:00+00:00")
    assert any(d["id"] == "remote-uuid-1234" for d in doses)


def test_merge_remote_doses_update_deleted(store: Store) -> None:
    dose_id = store.add_dose(
        timestamp="2026-03-10T09:00:00+00:00", beverage="coffee", caffeine_mg=95
    )
    # Remote says this dose was deleted at a later time.
    remote_doses: list[dict[str, object]] = [
        {
            "id": dose_id,
            "machine_id": "machine-aaa",
            "timestamp": "2026-03-10T09:00:00+00:00",
            "beverage": "coffee",
            "caffeine_mg": 95.0,
            "count": 1,
            "deleted": 1,
            "created_at": "2026-03-10T09:00:00+00:00",
            "updated_at": "2099-01-01T00:00:00+00:00",  # Far future → wins.
        }
    ]
    inserted, updated = store.merge_remote_doses(remote_doses)
    assert inserted == 0
    assert updated == 1

    # Should now be soft-deleted.
    assert store.get_active_doses(since="2026-03-10T00:00:00+00:00") == []


def test_merge_remote_doses_skip_stale(store: Store) -> None:
    dose_id = store.add_dose(
        timestamp="2026-03-10T09:00:00+00:00", beverage="coffee", caffeine_mg=95
    )
    remote_doses: list[dict[str, object]] = [
        {
            "id": dose_id,
            "machine_id": "machine-aaa",
            "timestamp": "2026-03-10T09:00:00+00:00",
            "beverage": "coffee",
            "caffeine_mg": 95.0,
            "count": 1,
            "deleted": 1,
            "created_at": "2026-03-10T09:00:00+00:00",
            "updated_at": "2000-01-01T00:00:00+00:00",  # Ancient → skip.
        }
    ]
    inserted, updated = store.merge_remote_doses(remote_doses)
    assert inserted == 0
    assert updated == 0

    # Still active.
    assert len(store.get_active_doses(since="2026-03-10T00:00:00+00:00")) == 1


# ── config (JSON) ────────────────────────────────────────────────────


def test_load_config_generates_machine_id(config_path: Path) -> None:
    config = Store.load_config(config_path)
    assert config["machine_id"] is not None
    assert isinstance(config["machine_id"], str)
    assert config["half_life_hours"] == 5.0

    # Should persist.
    assert config_path.exists()
    data = json.loads(config_path.read_text())
    assert data["machine_id"] == config["machine_id"]


def test_load_config_preserves_existing(config_path: Path) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps({"half_life_hours": 9, "machine_id": "custom-id"}))

    config = Store.load_config(config_path)
    assert config["half_life_hours"] == 9
    assert config["machine_id"] == "custom-id"
