# Development Plan: `hisspresso` Caffeine Tracker

## Overview

A CLI tool to log caffeine intake and visualize residual caffeine over time, modeling pharmacokinetic decay with optional personalization.

---

## Architecture

**File layout:**
```
src/hisspresso/
    __init__.py       ← entry point, wires CLI
    cli.py            ← command definitions (log, show, config, list, sync)
    storage.py        ← SQLite database access + config JSON read/write
    beverages.py      ← built-in beverage → caffeine mg database
    model.py          ← caffeine decay / pharmacokinetics
    graph.py          ← terminal graph rendering
    sync.py           ← merge-based sync: export, import, conflict resolution
```

**Data files (stored in user data dir via `platformdirs`):**
- `hisspresso.db` — SQLite database (see [Storage](#storage) below)
- `config.json` — user profile: `{half_life_hours, machine_id}` (kept as JSON for easy hand-editing)

---

## Timestamps

All timestamps are stored as **UTC ISO 8601** strings (`2026-03-10T14:30:00+00:00`).

**On input:**
- Bare times like `--at "14:30"` are interpreted as **local time today** and converted to UTC before storage.
- Date-times like `--at "2026-03-09 21:00"` are interpreted as local time and converted to UTC.
- If no `--at` flag is given, `datetime.now(timezone.utc)` is used.

**On display:**
- All timestamps are converted from UTC to the user's **local timezone** (via `datetime.astimezone()`) before rendering in `list`, `show`, or graph labels.

This avoids ambiguity when users travel or when DST transitions occur.

---

## Pharmacokinetics Model

Residual caffeine from a single dose follows first-order exponential decay:

```
C(t) = dose_mg × 0.5^( (t - t_dose) / t_half )
```

Total residual at time `t` = sum over all logged doses within a reasonable window (~5× half-life).

**Default half-life: 5 hours.** User-configurable, with notes:
- Biological sex (especially female + hormonal contraceptives) increases half-life to ~9–11 h
- Smokers: ~3 h
- Body weight affects mg/kg effective dose display but not decay rate directly

---

## CLI Commands

| Command | Description |
|---|---|
| `hisspresso log <beverage>` | Log a known beverage (looks up caffeine mg) |
| `hisspresso log <beverage> --caffeine 120` | Log with explicit caffeine amount |
| `hisspresso log <beverage> --count 2` | Log multiple servings |
| `hisspresso log <beverage> --at "14:30"` | Log at a specific time today (local) |
| `hisspresso log <beverage> --at "2026-03-09 21:00"` | Log at a specific date-time (local) |
| `hisspresso undo` | Soft-delete the most recent dose |
| `hisspresso delete <id>` | Soft-delete a specific dose by short ID prefix |
| `hisspresso restore <id>` | Restore a soft-deleted dose by short ID prefix |
| `hisspresso show` | Display residual caffeine graph |
| `hisspresso show --hours 48` | Graph over a wider window |
| `hisspresso list` | Show recent log entries (with IDs) |
| `hisspresso list --deleted` | Show soft-deleted entries |
| `hisspresso beverages` | List all known beverages (built-in + custom) |
| `hisspresso beverages add <name> --caffeine <mg>` | Add a custom beverage |
| `hisspresso beverages remove <name>` | Remove a custom beverage |
| `hisspresso config set --half-life 9` | Set half-life |
| `hisspresso config set --sync-dir "/path/to/folder"` | Set sync directory |
| `hisspresso config show` | Show current profile |
| `hisspresso purge` | Hard-delete soft-deleted entries older than 30 days |
| `hisspresso sync push` | Export local changes to sync directory |
| `hisspresso sync pull` | Import remote changes from sync directory |
| `hisspresso sync status` | Show sync config and last sync time |

---

## Beverage Database

Beverages live in two layers:

### 1. Built-in defaults (hardcoded in `beverages.py`)

| Key | Aliases | Caffeine (mg) |
|---|---|---|
| `espresso` | `shot` | 63 |
| `coffee` | `drip`, `filter` | 95 |
| `americano` | | 95 |
| `latte` | | 63 |
| `cold-brew` | `cold brew`, `coldbrew` | 155 |
| `green-tea` | `green tea` | 30 |
| `black-tea` | `black tea` | 50 |
| `matcha` | | 70 |
| `red-bull` | `red bull`, `redbull` | 80 |
| `monster` | | 160 |

Each entry is a dict: `{key, aliases, caffeine_mg}`. Lookup is case-insensitive and checks both `key` and `aliases`.

### 2. User-defined beverages (stored in `hisspresso.db`)

Users can add custom beverages:

```
hisspresso beverages add "oat latte" --caffeine 63
hisspresso beverages add "yerba mate" --caffeine 85
hisspresso beverages remove "oat latte"
```

Custom beverages are stored in a `beverages` table and are checked **before** built-ins, so users can override defaults (e.g., redefine `coffee` as 120 mg for their preferred brew).

`hisspresso beverages` lists both built-in and custom entries, with custom ones marked.

### Multipliers

Instead of fuzzy-parsing "double espresso", support an explicit `--count` flag:

```
hisspresso log espresso --count 2    # logs 126 mg
```

This is predictable and avoids ambiguity.

---

## Graph

Terminal-based using **`plotext`** (keeps it self-contained, no GUI). The graph shows:
- X-axis: time window (e.g. last 24 h, centered on now)
- Y-axis: residual caffeine in mg
- Curve: total residual caffeine at each point
- Vertical markers: dose events (labeled with beverage name)
- Horizontal reference lines: rough effect thresholds (e.g. 50 mg = noticeable, 200 mg = high)
- "Now" cursor highlighted

---

## Storage

SQLite via Python's built-in `sqlite3` module. Single database file `hisspresso.db` in the user data dir.

### Schema (v1)

```sql
-- Version tracking
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', '1');

-- Caffeine dose log
CREATE TABLE IF NOT EXISTS doses (
    id          TEXT    PRIMARY KEY,                -- UUID v4, e.g. 'a1b2c3d4-...'
    machine_id  TEXT    NOT NULL,                   -- originating machine (from config.json)
    timestamp   TEXT    NOT NULL,                   -- UTC ISO 8601, when the dose was consumed
    beverage    TEXT    NOT NULL,                   -- beverage key at log time
    caffeine_mg REAL    NOT NULL CHECK (caffeine_mg > 0),
    count       INTEGER NOT NULL DEFAULT 1 CHECK (count >= 1),
    deleted     INTEGER NOT NULL DEFAULT 0 CHECK (deleted IN (0, 1)),
    created_at  TEXT    NOT NULL,                   -- UTC ISO 8601, when the row was inserted
    updated_at  TEXT    NOT NULL                    -- UTC ISO 8601, last modification (for sync)
);

-- Primary query path: active doses in a time window for the decay model
CREATE INDEX IF NOT EXISTS idx_doses_active
    ON doses (timestamp)
    WHERE deleted = 0;

-- For "undo" — find most recent non-deleted dose from this machine
CREATE INDEX IF NOT EXISTS idx_doses_undo
    ON doses (created_at DESC)
    WHERE deleted = 0;

-- For sync — find rows changed since last sync
CREATE INDEX IF NOT EXISTS idx_doses_sync
    ON doses (updated_at);

-- User-defined beverages (overrides built-ins)
CREATE TABLE IF NOT EXISTS beverages (
    key         TEXT PRIMARY KEY,                   -- lowercase, hyphenated, e.g. 'oat-latte'
    caffeine_mg REAL NOT NULL CHECK (caffeine_mg > 0),
    aliases     TEXT NOT NULL DEFAULT '',           -- comma-separated, e.g. 'oat latte,oatlatte'
    updated_at  TEXT NOT NULL                       -- UTC ISO 8601, for sync
);
```

### Key design notes

- **UUID primary key** — `uuid.uuid4()` string. Avoids ID collisions across machines, enabling merge-based sync without coordination. CLI commands that accept an `<id>` argument match by **shortest unique prefix** (like git short hashes), so users type `hisspresso delete a1b2` instead of the full UUID.
- **`machine_id`** — identifies which machine created the dose. Auto-generated (`uuid4`) on first run and stored in `config.json`. Used by `undo` (only undo your own machine's doses) and by sync (to partition changefeeds).
- **`updated_at`** — set to `created_at` on insert, updated on soft-delete or restore. The sync index on this column enables efficient "give me everything changed since my last sync."
- **`count` column** — stores the `--count` multiplier so `list` can display "2× espresso" rather than a single 126 mg mystery entry. The effective dose is `caffeine_mg * count`.
- **`created_at`** — distinguishes when the dose was *logged* from when it was *consumed* (`timestamp`). `undo` targets the most recently *created* row, not the most recent *timestamp*.
- **`CHECK` constraints** — prevent nonsense data at the database level.
- **Partial indexes** — `WHERE deleted = 0` keeps index size small and matches the default query filter.
- **`IF NOT EXISTS`** — all DDL is idempotent, safe to re-run on every startup.

### Why SQLite over JSON

- **Append-only writes** — logging a dose is an `INSERT`, not "read entire file → append → write entire file." No risk of corruption from concurrent access.
- **Efficient queries** — `SELECT` with `WHERE timestamp > ?` for the decay window, rather than loading every entry into memory.
- **Soft deletes and undo** — trivial with a `deleted` column (see below).
- **No new dependency** — `sqlite3` is in the standard library.

`config.json` stays as JSON since it's a small, rarely-changed blob that users may want to hand-edit.

### Undo / Delete Operations

Doses are **soft-deleted** — setting `deleted = 1` and updating `updated_at` rather than removing the row. This enables undo and syncs the deletion to other machines:

```
hisspresso undo                     # soft-deletes the most recent dose (this machine only)
hisspresso delete a1b2              # soft-deletes a dose by UUID prefix
hisspresso list --deleted           # show soft-deleted entries
hisspresso restore a1b2             # un-deletes a dose by UUID prefix
```

`undo` filters on `machine_id = <this machine>` so you only undo your own entries, even after pulling doses from other machines.

All queries (`show`, `list`, model calculations) filter on `WHERE deleted = 0` by default.

Periodically (or via `hisspresso purge`), soft-deleted rows older than 30 days can be hard-deleted to keep the database lean.

### Migrations

On startup, `storage.py` reads `schema_version` from the `meta` table and applies any pending migrations sequentially. Each migration is a function in a list:

```python
MIGRATIONS = [
    # v0 → v1: initial schema (applied via CREATE IF NOT EXISTS above)
    # v1 → v2: (future) e.g. add a "notes" column to doses
]
```

If `meta` doesn't exist, the database is new — run the full v1 DDL and set `schema_version = '1'`.

### `storage.py` API surface

```python
class Store:
    def __init__(self, db_path: Path, machine_id: str):
        """Open or create the database, run migrations. machine_id from config."""

    # --- doses ---
    def add_dose(self, timestamp: str, beverage: str, caffeine_mg: float, count: int = 1) -> str:
        """INSERT a dose with a new UUID. Sets machine_id, created_at, updated_at. Returns the UUID."""

    def get_active_doses(self, since: str) -> list[dict]:
        """SELECT doses WHERE deleted=0 AND timestamp >= since."""

    def soft_delete(self, id_prefix: str) -> str | None:
        """Match UUID by prefix, SET deleted=1 and updated_at=now. Returns full UUID, or None."""

    def undo_last(self) -> str | None:
        """Soft-delete the most recently created non-deleted dose on this machine. Returns UUID."""

    def restore(self, id_prefix: str) -> str | None:
        """Match UUID by prefix, SET deleted=0 and updated_at=now. Returns full UUID, or None."""

    def resolve_id(self, prefix: str) -> str | None:
        """Find a unique dose UUID matching the given prefix. Returns None if 0 or >1 matches."""

    def list_doses(self, limit: int = 20, include_deleted: bool = False) -> list[dict]:
        """Recent doses, ordered by timestamp DESC."""

    def purge(self, older_than_days: int = 30) -> int:
        """Hard-delete soft-deleted rows older than N days. Returns count removed."""

    # --- sync ---
    def get_changes_since(self, since: str) -> list[dict]:
        """All doses (including deleted) with updated_at > since. For sync export."""

    def merge_remote_doses(self, doses: list[dict]) -> tuple[int, int]:
        """Merge incoming doses. INSERT new UUIDs, update existing if remote updated_at is newer.
        Returns (inserted, updated) counts."""

    def get_beverage_changes_since(self, since: str) -> list[dict]:
        """Custom beverages with updated_at > since."""

    def merge_remote_beverages(self, beverages: list[dict]) -> tuple[int, int]:
        """Merge incoming custom beverages. Last-write-wins on updated_at."""

    # --- custom beverages ---
    def add_beverage(self, key: str, caffeine_mg: float, aliases: str = "") -> None:
        """INSERT OR REPLACE a custom beverage. Sets updated_at=now."""

    def remove_beverage(self, key: str) -> bool:
        """DELETE a custom beverage. Returns False if not found."""

    def get_custom_beverages(self) -> list[dict]:
        """All user-defined beverages."""

    # --- config (JSON) ---
    @staticmethod
    def load_config(config_path: Path) -> dict:
        """Read config.json, return defaults if missing. Auto-generates machine_id on first call."""

    @staticmethod
    def save_config(config_path: Path, config: dict) -> None:
        """Write config.json."""
```

---

## Sync

Merge-based sync allows the same user to log doses on multiple machines and combine them into a single view.

### Design principles

- **Local-first** — the local DB is always the source of truth for reads. Sync is an explicit action, not automatic.
- **Append-mostly** — doses are almost never edited after creation. The only mutation is soft-delete/restore, which is a single `deleted` flag resolved by last-write-wins on `updated_at`.
- **No central server required** — sync operates on a shared directory (Syncthing, Dropbox, OneDrive, network drive). A server transport can be added later without changing the merge logic.

### Shared directory layout

```
<sync-dir>/
    <machine_id_A>.jsonl      ← changefeed from machine A
    <machine_id_B>.jsonl      ← changefeed from machine B
    ...
```

Each `.jsonl` file contains one JSON object per line — a dose or beverage record, including all columns. The file is append-only; each `sync push` appends new/changed rows since the last push.

### Sync operations

**`hisspresso sync push`**
1. Read `last_push_at` from `meta` table (or epoch if first push)
2. Query `get_changes_since(last_push_at)` — all doses with `updated_at > last_push_at`
3. Query `get_beverage_changes_since(last_push_at)` — same for custom beverages
4. Append the rows as JSON lines to `<sync-dir>/<machine_id>.jsonl`
5. Update `last_push_at` in `meta`

**`hisspresso sync pull`**
1. For each `<other_machine_id>.jsonl` in the sync directory (skip own file):
   - Read `last_pull_<machine_id>` from `meta` (line offset, or 0 if first pull)
   - Read new lines from the file starting at that offset
   - Parse JSON lines into dose/beverage dicts
   - Call `merge_remote_doses()` and `merge_remote_beverages()`
   - Update the line offset in `meta`
2. Print summary: "Pulled 3 new doses, updated 1"

**`hisspresso sync status`**
- Show sync directory path (or "not configured")
- Show `machine_id`
- Show `last_push_at` and `last_pull_*` timestamps

### Merge rules

| Scenario | Action |
|---|---|
| UUID not in local DB | `INSERT` the remote row as-is |
| UUID exists, remote `updated_at` > local `updated_at` | Update `deleted` and `updated_at` to remote values |
| UUID exists, remote `updated_at` <= local `updated_at` | Skip (local is newer or same) |

This is a simple **last-write-wins** strategy on the `deleted` flag. Since `caffeine_mg`, `beverage`, `count`, and `timestamp` are immutable after creation, the only field that can diverge is `deleted`.

### Configuration

```
hisspresso config set --sync-dir "/path/to/shared/folder"
```

Stored in `config.json` as `sync_dir`. If not set, `sync` commands print an error with setup instructions.

---

## Dependencies

```toml
dependencies = [
    "click",          # CLI framework
    "plotext",        # terminal plotting
    "platformdirs",   # cross-platform data directory
]
```

`sqlite3` is stdlib — no extra dependency needed.

Optional later: `rich` for nicer table output in `list` / `beverages`.

---

## Implementation Phases

### Phase 1 — Storage layer (`storage.py`)
- `Store` class: open/create SQLite database, run DDL, handle migrations
- Implement all `Store` methods (see API surface above)
- `load_config` / `save_config` for `config.json`
- Path resolution via `platformdirs.user_data_dir("hisspresso")`
- **Test**: round-trip `add_dose` → `get_active_doses`, soft-delete → restore, `purge`

### Phase 2 — Beverage lookup (`beverages.py`)
- Built-in beverage dict with aliases
- `lookup(name: str) -> dict | None` — case-insensitive match against keys and aliases
- Integration with `Store.get_custom_beverages()` — custom checked first, then built-ins
- `list_all()` — merged view of custom + built-in, custom entries marked
- **Test**: alias resolution, custom override of built-in, case-insensitive match

### Phase 3 — CLI scaffold + `log` command (`cli.py`, `__init__.py`)
- `click` group with `log` subcommand
- `--caffeine`, `--count`, `--at` options
- Timestamp parsing: bare time → local today → UTC; date-time → UTC; absent → `utcnow()`
- Beverage lookup → resolve caffeine mg → `Store.add_dose()`
- Error: unknown beverage without `--caffeine` → suggest `beverages` command
- `pyproject.toml` `[project.scripts]` entry point
- **Test**: `--at` parsing edge cases (midnight, DST boundary)

### Phase 4 — Pharmacokinetics (`model.py`)
- `residual_caffeine(doses: list[dict], at: datetime, half_life: float) -> float`
- Sum of `caffeine_mg * count * 0.5^((t - t_dose) / half_life)` for each dose
- `caffeine_curve(doses, start, end, half_life, steps=200) -> list[tuple[datetime, float]]`
- Filter doses to `timestamp >= start - 5 * half_life` window
- **Test**: known decay values, multiple overlapping doses, empty dose list

### Phase 5 — Graph (`graph.py`)
- `plotext` integration: time series curve from `caffeine_curve()` output
- Vertical markers at dose timestamps (labeled with beverage name + count)
- Horizontal threshold lines (50 mg, 200 mg)
- "Now" cursor
- Adapt to terminal width via `plotext.terminal_size()`
- `--hours` flag (default 24)
- **Test**: manual visual verification (no automated graph tests)

### Phase 6 — Remaining commands
- `undo` — `Store.undo_last()`, print what was removed
- `delete <id>` / `restore <id>` — by dose ID
- `list` — tabular output (ID, time in local tz, beverage, caffeine, count); `--deleted` flag
- `beverages` — merged list; `beverages add` / `beverages remove` subcommands
- `config show` / `config set --half-life` — read/write `config.json`
- `purge` — `Store.purge()`, print count removed
- **Test**: `list --deleted` shows only soft-deleted entries

### Phase 7 — Sync (`sync.py`)
- `export_changes(store, sync_dir, machine_id)` — append new rows to `.jsonl`
- `import_changes(store, sync_dir, machine_id)` — read other machines' `.jsonl`, call merge methods
- `sync push` / `sync pull` / `sync status` CLI commands
- `config set --sync-dir` option
- Track `last_push_at` and `last_pull_<machine_id>` in `meta` table
- **Test**: two in-memory stores simulate push/pull cycle; merge conflict (same UUID, different `deleted` states) resolves to latest `updated_at`

### Phase 8 — Polish
- `--help` text for every command and option
- Friendly error messages (unknown beverage, invalid time format, dose ID not found)
- Confirm prompt for `purge`
- `__main__.py` for `python -m hisspresso` support

---

## Resolved Decisions

1. **Half-life personalization** → manual only via `config set --half-life`. No `--sex` or `--weight` — keeps config minimal and avoids storing demographic data for marginal benefit. Documentation will note typical ranges (smokers ~3h, contraceptive use ~9-11h, default 5h).
2. **Graph window** → default 24h, anchored at `now - 24h` to `now`.
3. **Double espresso** → `--count 2` flag. No name parsing.
4. **Storage format** → SQLite (see [Storage](#storage) section).
5. **Caffeine thresholds on graph** → yes, keep them. Useful reference at a glance.

## Open Questions

1. **Absorption delay**: model a ~45 min ramp-up before decay, or keep the instant-peak simplification for v1?
2. **Graph clutter**: collapse nearby dose markers when >3 events overlap within a short window?
