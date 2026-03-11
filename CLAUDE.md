# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**hisspresso** — a CLI caffeine intake tracker for the terminal. Users log beverages, and the tool models pharmacokinetic decay to show residual caffeine over time via terminal graphs.

## Build & Run

This project uses **uv** as the package manager and build backend (`uv_build`). Python >=3.13 required.

```bash
uv sync                        # install dependencies into .venv
uv run hisspresso               # run the CLI entry point
uv run python -m pytest         # run tests
uv run python -m pytest tests/test_storage.py::test_add_dose  # single test
uv run ruff check src tests     # lint
uv run ruff format src tests    # auto-format
uv run mypy                     # type check (strict)
```

The CLI entry point is defined in `pyproject.toml` as `hisspresso = "hisspresso:main"`.

## Architecture

Source lives in `src/hisspresso/`. The planned module structure:

| Module | Role |
|---|---|
| `__init__.py` | Entry point, wires CLI |
| `cli.py` | Click command definitions (log, show, config, list, sync, etc.) |
| `storage.py` | SQLite database access (`Store` class) + config JSON read/write |
| `beverages.py` | Built-in beverage→caffeine-mg lookup with aliases; custom beverage support |
| `model.py` | Pharmacokinetic decay: `C(t) = dose_mg × 0.5^((t - t_dose) / t_half)` |
| `graph.py` | Terminal graph rendering via `plotext` |
| `sync.py` | Merge-based sync: export/import via shared directory (JSONL changefeeds) |

**Data storage**: SQLite (`hisspresso.db`) via stdlib `sqlite3` in the user data dir (`platformdirs`). Config is a separate `config.json` for hand-editability.

**Dependencies**: `click` (CLI), `plotext` (terminal plotting), `platformdirs` (cross-platform paths).

## Key Design Conventions

- **Timestamps**: stored as UTC ISO 8601. Bare input times (e.g. `--at "14:30"`) are interpreted as local time and converted to UTC before storage. Display always converts back to local timezone.
- **IDs**: UUID v4 primary keys. CLI commands accept shortest unique prefix (like git short hashes).
- **Soft deletes**: doses use a `deleted` column (0/1) rather than hard deletes, enabling undo and sync.
- **Sync**: last-write-wins on `updated_at` for the `deleted` flag. Dose content fields are immutable after creation.
- **Beverage lookup**: case-insensitive, checks custom beverages first, then built-in defaults.
- **`machine_id`**: auto-generated UUID stored in `config.json`, used to scope `undo` to the current machine.

## Code Quality

Dev tools are in the `dev` dependency group (`uv sync` installs them automatically).

- **Ruff**: linting (`E/F/W/I/UP/B` rules) and formatting. Line length 99.
- **Mypy**: strict mode, covers `src/` and `tests/`.
- **Pytest**: tests live in `tests/`, discovered by default conventions.

All three must pass cleanly before committing.

## Development Plan

See `artifacts/plan.md` for the full implementation plan with phases, schema DDL, API surface, CLI command table, and design decisions.
