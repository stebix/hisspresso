"""SQLite database access and JSON config read/write."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

DDL_V1 = """\
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', '1');

CREATE TABLE IF NOT EXISTS doses (
    id          TEXT    PRIMARY KEY,
    machine_id  TEXT    NOT NULL,
    timestamp   TEXT    NOT NULL,
    beverage    TEXT    NOT NULL,
    caffeine_mg REAL    NOT NULL CHECK (caffeine_mg > 0),
    count       INTEGER NOT NULL DEFAULT 1 CHECK (count >= 1),
    deleted     INTEGER NOT NULL DEFAULT 0 CHECK (deleted IN (0, 1)),
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_doses_active
    ON doses (timestamp)
    WHERE deleted = 0;

CREATE INDEX IF NOT EXISTS idx_doses_undo
    ON doses (created_at DESC)
    WHERE deleted = 0;

CREATE INDEX IF NOT EXISTS idx_doses_sync
    ON doses (updated_at);

CREATE TABLE IF NOT EXISTS beverages (
    key         TEXT PRIMARY KEY,
    caffeine_mg REAL NOT NULL CHECK (caffeine_mg > 0),
    aliases     TEXT NOT NULL DEFAULT '',
    updated_at  TEXT NOT NULL
);
"""

# Future migrations go here as callables taking a sqlite3.Connection.
MIGRATIONS: list[tuple[str, str]] = [
    # ("1", "2", migrate_v1_to_v2),
]

DEFAULT_CONFIG: dict[str, object] = {
    "half_life_hours": 5.0,
    "machine_id": None,
    "sync_dir": None,
    "theme": "dark",
}


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


def _dict_row(cursor: sqlite3.Cursor, row: tuple[object, ...]) -> dict[str, object]:
    """Row factory that returns dicts keyed by column name."""
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


class Store:
    """Thin wrapper around a hisspresso SQLite database."""

    def __init__(self, db_path: Path, machine_id: str) -> None:
        self._machine_id = machine_id
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = _dict_row  # type: ignore[assignment]
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    # ── schema / migrations ──────────────────────────────────────────

    def _init_schema(self) -> None:
        self._conn.executescript(DDL_V1)
        # Apply any pending sequential migrations.
        version = self._schema_version()
        for from_ver, to_ver in MIGRATIONS:
            if version == from_ver:
                # Each entry would also carry a callable; extend when needed.
                version = to_ver

    def _schema_version(self) -> str:
        row = self._conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        return row["value"] if row else "0"  # type: ignore[index]

    # ── doses ────────────────────────────────────────────────────────

    def add_dose(
        self,
        timestamp: str,
        beverage: str,
        caffeine_mg: float,
        count: int = 1,
    ) -> str:
        dose_id = str(uuid.uuid4())
        now = _now_utc()
        self._conn.execute(
            """INSERT INTO doses
               (id, machine_id, timestamp, beverage, caffeine_mg,
                count, deleted, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)""",
            (dose_id, self._machine_id, timestamp, beverage, caffeine_mg, count, now, now),
        )
        self._conn.commit()
        return dose_id

    def get_active_doses(self, since: str) -> list[dict[str, object]]:
        return self._conn.execute(
            "SELECT * FROM doses WHERE deleted = 0 AND timestamp >= ? ORDER BY timestamp",
            (since,),
        ).fetchall()

    def resolve_id(self, prefix: str) -> str | None:
        rows = self._conn.execute(
            "SELECT id FROM doses WHERE id LIKE ? || '%'",
            (prefix,),
        ).fetchall()
        if len(rows) == 1:
            return rows[0]["id"]  # type: ignore[return-value]
        return None

    def soft_delete(self, id_prefix: str) -> str | None:
        full_id = self.resolve_id(id_prefix)
        if full_id is None:
            return None
        now = _now_utc()
        cur = self._conn.execute(
            "UPDATE doses SET deleted = 1, updated_at = ? WHERE id = ? AND deleted = 0",
            (now, full_id),
        )
        self._conn.commit()
        return full_id if cur.rowcount > 0 else None

    def undo_last(self) -> str | None:
        row = self._conn.execute(
            """SELECT id FROM doses
               WHERE deleted = 0 AND machine_id = ?
               ORDER BY created_at DESC LIMIT 1""",
            (self._machine_id,),
        ).fetchone()
        if row is None:
            return None
        dose_id: str = row["id"]  # type: ignore[assignment]
        now = _now_utc()
        self._conn.execute(
            "UPDATE doses SET deleted = 1, updated_at = ? WHERE id = ?",
            (now, dose_id),
        )
        self._conn.commit()
        return dose_id

    def restore(self, id_prefix: str) -> str | None:
        full_id = self.resolve_id(id_prefix)
        if full_id is None:
            return None
        now = _now_utc()
        cur = self._conn.execute(
            "UPDATE doses SET deleted = 0, updated_at = ? WHERE id = ? AND deleted = 1",
            (now, full_id),
        )
        self._conn.commit()
        return full_id if cur.rowcount > 0 else None

    def list_doses(
        self, limit: int = 20, include_deleted: bool = False
    ) -> list[dict[str, object]]:
        if include_deleted:
            return self._conn.execute(
                "SELECT * FROM doses ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return self._conn.execute(
            "SELECT * FROM doses WHERE deleted = 0 ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()

    def purge(self, older_than_days: int = 30) -> int:
        from datetime import timedelta

        cutoff = (datetime.now(UTC) - timedelta(days=older_than_days)).isoformat()
        cur = self._conn.execute(
            "DELETE FROM doses WHERE deleted = 1 AND updated_at < ?",
            (cutoff,),
        )
        self._conn.commit()
        return cur.rowcount

    # ── sync helpers ─────────────────────────────────────────────────

    def get_changes_since(self, since: str) -> list[dict[str, object]]:
        return self._conn.execute(
            "SELECT * FROM doses WHERE updated_at > ? ORDER BY updated_at",
            (since,),
        ).fetchall()

    def merge_remote_doses(self, doses: list[dict[str, object]]) -> tuple[int, int]:
        inserted = 0
        updated = 0
        for dose in doses:
            existing = self._conn.execute(
                "SELECT updated_at FROM doses WHERE id = ?", (dose["id"],)
            ).fetchone()
            if existing is None:
                self._conn.execute(
                    """INSERT INTO doses
                       (id, machine_id, timestamp, beverage, caffeine_mg,
                        count, deleted, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        dose["id"],
                        dose["machine_id"],
                        dose["timestamp"],
                        dose["beverage"],
                        dose["caffeine_mg"],
                        dose["count"],
                        dose["deleted"],
                        dose["created_at"],
                        dose["updated_at"],
                    ),
                )
                inserted += 1
            elif dose["updated_at"] > existing["updated_at"]:  # type: ignore[operator]
                self._conn.execute(
                    "UPDATE doses SET deleted = ?, updated_at = ? WHERE id = ?",
                    (dose["deleted"], dose["updated_at"], dose["id"]),
                )
                updated += 1
        self._conn.commit()
        return inserted, updated

    def get_beverage_changes_since(self, since: str) -> list[dict[str, object]]:
        return self._conn.execute(
            "SELECT * FROM beverages WHERE updated_at > ? ORDER BY updated_at",
            (since,),
        ).fetchall()

    def merge_remote_beverages(self, beverages: list[dict[str, object]]) -> tuple[int, int]:
        inserted = 0
        updated = 0
        for bev in beverages:
            existing = self._conn.execute(
                "SELECT updated_at FROM beverages WHERE key = ?", (bev["key"],)
            ).fetchone()
            if existing is None:
                self._conn.execute(
                    """INSERT INTO beverages (key, caffeine_mg, aliases, updated_at)
                       VALUES (?, ?, ?, ?)""",
                    (bev["key"], bev["caffeine_mg"], bev["aliases"], bev["updated_at"]),
                )
                inserted += 1
            elif bev["updated_at"] > existing["updated_at"]:  # type: ignore[operator]
                self._conn.execute(
                    """UPDATE beverages
                       SET caffeine_mg = ?, aliases = ?, updated_at = ?
                       WHERE key = ?""",
                    (bev["caffeine_mg"], bev["aliases"], bev["updated_at"], bev["key"]),
                )
                updated += 1
        self._conn.commit()
        return inserted, updated

    # ── custom beverages ─────────────────────────────────────────────

    def add_beverage(self, key: str, caffeine_mg: float, aliases: str = "") -> None:
        now = _now_utc()
        self._conn.execute(
            """INSERT OR REPLACE INTO beverages (key, caffeine_mg, aliases, updated_at)
               VALUES (?, ?, ?, ?)""",
            (key, caffeine_mg, aliases, now),
        )
        self._conn.commit()

    def remove_beverage(self, key: str) -> bool:
        cur = self._conn.execute("DELETE FROM beverages WHERE key = ?", (key,))
        self._conn.commit()
        return cur.rowcount > 0

    def get_custom_beverages(self) -> list[dict[str, object]]:
        return self._conn.execute("SELECT * FROM beverages ORDER BY key").fetchall()

    # ── meta helpers ─────────────────────────────────────────────────

    def get_meta(self, key: str) -> str | None:
        row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None  # type: ignore[index]

    def set_meta(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            (key, value),
        )
        self._conn.commit()

    # ── config (JSON) ────────────────────────────────────────────────

    @staticmethod
    def load_config(config_path: Path) -> dict[str, object]:
        config = dict(DEFAULT_CONFIG)
        if config_path.exists():
            with open(config_path) as f:
                config.update(json.load(f))
        # Auto-generate machine_id on first access.
        if not config.get("machine_id"):
            config["machine_id"] = str(uuid.uuid4())
            Store.save_config(config_path, config)
        return config

    @staticmethod
    def save_config(config_path: Path, config: dict[str, object]) -> None:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
            f.write("\n")

    def close(self) -> None:
        self._conn.close()
