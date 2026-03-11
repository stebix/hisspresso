"""Merge-based sync via a shared directory of JSONL changefeeds."""

from __future__ import annotations

import json
from pathlib import Path

from hisspresso.storage import Store, _now_utc


def push(store: Store, sync_dir: Path, machine_id: str) -> int:
    """Export local changes since last push to the sync directory.

    Returns the number of records written.
    """
    sync_dir.mkdir(parents=True, exist_ok=True)
    last_push = store.get_meta("last_push_at") or "1970-01-01T00:00:00+00:00"

    dose_changes = store.get_changes_since(last_push)
    bev_changes = store.get_beverage_changes_since(last_push)

    if not dose_changes and not bev_changes:
        return 0

    feed_path = sync_dir / f"{machine_id}.jsonl"
    with open(feed_path, "a") as f:
        for dose in dose_changes:
            record = {"type": "dose", **dose}
            f.write(json.dumps(record, default=str) + "\n")
        for bev in bev_changes:
            record = {"type": "beverage", **bev}
            f.write(json.dumps(record, default=str) + "\n")

    store.set_meta("last_push_at", _now_utc())
    return len(dose_changes) + len(bev_changes)


def pull(store: Store, sync_dir: Path, machine_id: str) -> tuple[int, int]:
    """Import changes from other machines' changefeeds.

    Returns (total_inserted, total_updated) across doses and beverages.
    """
    if not sync_dir.exists():
        return 0, 0

    total_inserted = 0
    total_updated = 0

    for feed_path in sync_dir.glob("*.jsonl"):
        remote_id = feed_path.stem
        if remote_id == machine_id:
            continue  # Skip own feed.

        offset_key = f"last_pull_offset_{remote_id}"
        offset = int(store.get_meta(offset_key) or "0")

        with open(feed_path) as f:
            lines = f.readlines()

        new_lines = lines[offset:]
        if not new_lines:
            continue

        doses: list[dict[str, object]] = []
        beverages: list[dict[str, object]] = []

        for line in new_lines:
            record = json.loads(line)
            rec_type = record.pop("type", None)
            if rec_type == "dose":
                doses.append(record)
            elif rec_type == "beverage":
                beverages.append(record)

        if doses:
            ins, upd = store.merge_remote_doses(doses)
            total_inserted += ins
            total_updated += upd

        if beverages:
            ins, upd = store.merge_remote_beverages(beverages)
            total_inserted += ins
            total_updated += upd

        store.set_meta(offset_key, str(len(lines)))

    return total_inserted, total_updated
