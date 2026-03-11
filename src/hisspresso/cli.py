"""CLI command definitions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import click
from platformdirs import user_data_dir

from hisspresso import beverages as bev_mod
from hisspresso.storage import Store

_DATA_DIR = Path(user_data_dir("hisspresso"))
_DB_PATH = _DATA_DIR / "hisspresso.db"
_CONFIG_PATH = _DATA_DIR / "config.json"


def _get_store() -> Store:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    config = Store.load_config(_CONFIG_PATH)
    return Store(_DB_PATH, machine_id=str(config["machine_id"]))


def _get_config() -> dict[str, object]:
    return Store.load_config(_CONFIG_PATH)


def _parse_at(value: str | None) -> str:
    """Parse --at value to UTC ISO 8601 string."""
    if value is None:
        return datetime.now(UTC).isoformat()

    from datetime import date as _date

    raw = value.strip()

    # Try full date-time first: "2026-03-09 21:00" or ISO format.
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M"):
        try:
            local_dt = datetime.strptime(raw, fmt).astimezone()
            return local_dt.astimezone(UTC).isoformat()
        except ValueError:
            continue

    # Try bare time: "14:30".
    try:
        t = datetime.strptime(raw, "%H:%M").time()
        today = _date.today()
        local_dt = datetime.combine(today, t).astimezone()
        return local_dt.astimezone(UTC).isoformat()
    except ValueError:
        pass

    raise click.BadParameter(f"Cannot parse '{value}'. Use HH:MM or YYYY-MM-DD HH:MM.")


def _parse_boundary(value: str) -> datetime:
    """Parse a --from/--to boundary value to a UTC-aware datetime."""
    from datetime import date as _date

    raw = value.strip()

    # Full date-time: "2026-03-09 21:00" or "2026-03-09T21:00".
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M"):
        try:
            local_dt = datetime.strptime(raw, fmt).astimezone()
            return local_dt.astimezone(UTC)
        except ValueError:
            continue

    # Date only: "2026-03-09" → start of that day, local time.
    try:
        local_dt = datetime.strptime(raw, "%Y-%m-%d").astimezone()
        return local_dt.astimezone(UTC)
    except ValueError:
        pass

    # Bare time: "14:30" → today, local time.
    try:
        t = datetime.strptime(raw, "%H:%M").time()
        today = _date.today()
        local_dt = datetime.combine(today, t).astimezone()
        return local_dt.astimezone(UTC)
    except ValueError:
        pass

    raise click.BadParameter(
        f"Cannot parse '{value}'. Use HH:MM, YYYY-MM-DD, or YYYY-MM-DD HH:MM."
    )


def _format_local(iso_utc: str) -> str:
    """Convert a UTC ISO timestamp to a local-time display string."""
    dt = datetime.fromisoformat(iso_utc).astimezone()
    return dt.strftime("%Y-%m-%d %H:%M")


# ── CLI group ────────────────────────────────────────────────────────


@click.group()
def cli() -> None:
    """hisspresso — caffeine intake tracker."""


# ── log ──────────────────────────────────────────────────────────────


@cli.command()
@click.argument("beverage")
@click.option("--caffeine", type=float, default=None, help="Explicit caffeine amount in mg.")
@click.option("--count", type=int, default=1, help="Number of servings.", show_default=True)
@click.option("--at", "at_time", default=None, help="Time of intake (HH:MM or YYYY-MM-DD HH:MM).")
def log(beverage: str, caffeine: float | None, count: int, at_time: str | None) -> None:
    """Log a caffeine dose."""
    store = _get_store()
    try:
        custom = store.get_custom_beverages()
        match = bev_mod.lookup(beverage, custom_beverages=custom)

        if caffeine is not None:
            mg = caffeine
            bev_key = beverage
        elif match is not None:
            mg = match.caffeine_mg
            bev_key = match.key
        else:
            raise click.ClickException(
                f"Unknown beverage '{beverage}'. "
                "Use --caffeine to specify mg, or run 'hisspresso beverages' to see known drinks."
            )

        ts = _parse_at(at_time)
        dose_id = store.add_dose(timestamp=ts, beverage=bev_key, caffeine_mg=mg, count=count)

        total_mg = mg * count
        short_id = dose_id[:8]
        click.echo(f"Logged {count}× {bev_key} ({total_mg:.0f} mg) [{short_id}]")
    finally:
        store.close()


# ── undo / delete / restore ──────────────────────────────────────────


@cli.command()
def undo() -> None:
    """Soft-delete the most recent dose (this machine only)."""
    store = _get_store()
    try:
        dose_id = store.undo_last()
        if dose_id:
            click.echo(f"Undone [{dose_id[:8]}]")
        else:
            click.echo("Nothing to undo.")
    finally:
        store.close()


@cli.command()
@click.argument("id_prefix")
def delete(id_prefix: str) -> None:
    """Soft-delete a dose by ID prefix."""
    store = _get_store()
    try:
        full_id = store.soft_delete(id_prefix)
        if full_id:
            click.echo(f"Deleted [{full_id[:8]}]")
        else:
            raise click.ClickException(f"No unique active dose found matching '{id_prefix}'.")
    finally:
        store.close()


@cli.command()
@click.argument("id_prefix")
def restore(id_prefix: str) -> None:
    """Restore a soft-deleted dose by ID prefix."""
    store = _get_store()
    try:
        full_id = store.restore(id_prefix)
        if full_id:
            click.echo(f"Restored [{full_id[:8]}]")
        else:
            raise click.ClickException(f"No unique deleted dose found matching '{id_prefix}'.")
    finally:
        store.close()


# ── show (graph) ─────────────────────────────────────────────────────


@cli.command()
@click.option("--hours", type=int, default=None, help="Show the last N hours (default: auto).")
@click.option(
    "--from",
    "from_time",
    default=None,
    help="Window start (HH:MM or YYYY-MM-DD HH:MM). Implies local timezone.",
)
@click.option(
    "--to",
    "to_time",
    default=None,
    help="Window end (HH:MM or YYYY-MM-DD HH:MM). Defaults to now.",
)
@click.option(
    "--theme",
    "theme_name",
    default=None,
    help="Graph theme name (overrides config). See bundled or user themes.",
)
def show(
    hours: int | None,
    from_time: str | None,
    to_time: str | None,
    theme_name: str | None,
) -> None:
    """Display residual caffeine graph.

    Without flags the x-axis is auto-ranged to cover all doses whose residual
    caffeine is still above 1 mg.  Use --hours for a simple "last N hours"
    view, or --from/--to for an explicit window.
    """
    from hisspresso.graph import render
    from hisspresso.graph_theme import load_graph_theme

    if hours is not None and (from_time is not None or to_time is not None):
        raise click.UsageError("--hours cannot be combined with --from/--to.")

    start = _parse_boundary(from_time) if from_time else None
    end = _parse_boundary(to_time) if to_time else None

    store = _get_store()
    config = _get_config()
    try:
        half_life = float(config.get("half_life_hours", 5.0))  # type: ignore[arg-type]

        resolved_theme = theme_name or str(config.get("theme", "dark"))
        try:
            theme = load_graph_theme(resolved_theme, data_dir=_DATA_DIR)
        except FileNotFoundError as exc:
            raise click.ClickException(str(exc)) from exc

        # Fetch doses generously — auto_window or explicit range will narrow display.
        lookback = max(hours or 48, 48) + half_life * 5
        since = (datetime.now(UTC) - timedelta(hours=lookback)).isoformat()
        doses = store.get_active_doses(since=since)
        if not doses:
            click.echo("No doses in the window. Log something first!")
            return
        render(doses, half_life_hours=half_life, start=start, end=end, hours=hours, theme=theme)
    finally:
        store.close()


# ── clear ────────────────────────────────────────────────────────────


@cli.command()
@click.option(
    "--threshold",
    type=float,
    default=10.0,
    help="Caffeine level in mg to consider 'clear'.",
    show_default=True,
)
def clear(threshold: float) -> None:
    """Show when caffeine drops below a threshold."""
    from hisspresso.model import residual_caffeine, time_to_threshold

    store = _get_store()
    config = _get_config()
    try:
        half_life = float(config.get("half_life_hours", 5.0))  # type: ignore[arg-type]
        lookback = 48 + half_life * 5
        now = datetime.now(UTC)
        since = (now - timedelta(hours=lookback)).isoformat()
        doses = store.get_active_doses(since=since)

        if not doses:
            click.echo("No doses logged.")
            return

        current = residual_caffeine(doses, at=now, half_life_hours=half_life)
        click.echo(f"Current caffeine : {current:.0f} mg")
        click.echo(f"Threshold        : {threshold:.0f} mg")

        clear_time = time_to_threshold(
            doses, threshold_mg=threshold, half_life_hours=half_life, _now=now
        )
        if clear_time is None:
            click.echo(f"You're already below {threshold:.0f} mg.")
        else:
            local_str = clear_time.astimezone().strftime("%Y-%m-%d %H:%M")
            delta = clear_time - now
            total_minutes = int(delta.total_seconds() / 60)
            hours, minutes = divmod(total_minutes, 60)
            click.echo(f"Clears at        : {local_str} (in {hours}h {minutes:02d}m)")
    finally:
        store.close()


# ── list ─────────────────────────────────────────────────────────────


@cli.command(name="list")
@click.option("--deleted", is_flag=True, help="Show soft-deleted entries.")
@click.option(
    "-n", "--limit", type=int, default=20, help="Max entries to show.", show_default=True
)
def list_doses(deleted: bool, limit: int) -> None:
    """Show recent log entries."""
    store = _get_store()
    try:
        doses = store.list_doses(limit=limit, include_deleted=deleted)
        if not doses:
            click.echo("No entries.")
            return

        header = f"{'ID':>8}  {'Time':<16}  {'Beverage':<14}  {'mg':>6}  {'#':>2}"
        if deleted:
            header += f"  {'Del':>3}"
        click.echo(header)
        click.echo("-" * len(header))

        for d in doses:
            short_id = str(d["id"])[:8]
            ts = _format_local(str(d["timestamp"]))
            bev = str(d["beverage"])
            mg = float(d["caffeine_mg"]) * int(d["count"])  # type: ignore[arg-type]
            count = int(d["count"])  # type: ignore[arg-type]
            line = f"{short_id:>8}  {ts:<16}  {bev:<14}  {mg:>6.0f}  {count:>2}"
            if deleted:
                del_flag = "yes" if d["deleted"] else ""
                line += f"  {del_flag:>3}"
            click.echo(line)
    finally:
        store.close()


# ── beverages ────────────────────────────────────────────────────────


@cli.group(invoke_without_command=True)
@click.pass_context
def beverages(ctx: click.Context) -> None:
    """List or manage known beverages."""
    if ctx.invoked_subcommand is not None:
        return
    store = _get_store()
    try:
        custom = store.get_custom_beverages()
        items = bev_mod.list_all(custom_beverages=custom)

        click.echo(f"{'Key':<14}  {'mg':>6}  {'Aliases':<24}  {'Src':<6}")
        click.echo("-" * 56)
        for item in items:
            src = "custom" if item["custom"] else ""
            aliases = str(item.get("aliases", ""))
            click.echo(
                f"{str(item['key']):<14}  {float(item['caffeine_mg']):>6.0f}"  # type: ignore[arg-type]
                f"  {aliases:<24}  {src:<6}"
            )
    finally:
        store.close()


@beverages.command(name="add")
@click.argument("name")
@click.option("--caffeine", required=True, type=float, help="Caffeine in mg.")
@click.option("--aliases", default="", help="Comma-separated aliases.")
def beverages_add(name: str, caffeine: float, aliases: str) -> None:
    """Add a custom beverage."""
    store = _get_store()
    try:
        key = name.strip().lower().replace(" ", "-")
        store.add_beverage(key, caffeine, aliases=aliases)
        click.echo(f"Added '{key}' ({caffeine:.0f} mg)")
    finally:
        store.close()


@beverages.command(name="remove")
@click.argument("name")
def beverages_remove(name: str) -> None:
    """Remove a custom beverage."""
    store = _get_store()
    try:
        key = name.strip().lower().replace(" ", "-")
        if store.remove_beverage(key):
            click.echo(f"Removed '{key}'")
        else:
            raise click.ClickException(f"Custom beverage '{key}' not found.")
    finally:
        store.close()


# ── config ───────────────────────────────────────────────────────────


@cli.group(invoke_without_command=True)
@click.pass_context
def config(ctx: click.Context) -> None:
    """View or modify configuration."""
    if ctx.invoked_subcommand is not None:
        return
    # Default: show config.
    ctx.invoke(config_show)


@config.command(name="show")
def config_show() -> None:
    """Show current configuration."""
    cfg = _get_config()
    click.echo(f"half_life_hours : {cfg.get('half_life_hours', 5.0)}")
    click.echo(f"theme           : {cfg.get('theme', 'dark')}")
    click.echo(f"machine_id      : {cfg.get('machine_id', '?')}")
    sync_dir = cfg.get("sync_dir")
    click.echo(f"sync_dir        : {sync_dir or '(not set)'}")
    click.echo(f"data_dir        : {_DATA_DIR}")


@config.command(name="set")
@click.option("--half-life", type=float, default=None, help="Caffeine half-life in hours.")
@click.option("--sync-dir", type=str, default=None, help="Path to sync directory.")
@click.option("--theme", type=str, default=None, help="Default graph theme name.")
def config_set(half_life: float | None, sync_dir: str | None, theme: str | None) -> None:
    """Update configuration values."""
    from hisspresso.graph_theme import load_graph_theme

    cfg = _get_config()
    changed = False
    if half_life is not None:
        cfg["half_life_hours"] = half_life
        changed = True
    if sync_dir is not None:
        cfg["sync_dir"] = sync_dir
        changed = True
    if theme is not None:
        # Validate that the theme actually exists before persisting.
        try:
            load_graph_theme(theme, data_dir=_DATA_DIR)
        except FileNotFoundError as exc:
            raise click.ClickException(str(exc)) from exc
        cfg["theme"] = theme
        changed = True
    if changed:
        Store.save_config(_CONFIG_PATH, cfg)
        click.echo("Config updated.")
    else:
        click.echo("Nothing to change. Use --half-life, --sync-dir, or --theme.")


# ── purge ────────────────────────────────────────────────────────────


@cli.command()
@click.option(
    "--days", type=int, default=30, help="Delete entries older than N days.", show_default=True
)
@click.confirmation_option(prompt="Permanently remove soft-deleted entries?")
def purge(days: int) -> None:
    """Hard-delete soft-deleted entries older than N days."""
    store = _get_store()
    try:
        count = store.purge(older_than_days=days)
        click.echo(f"Purged {count} entries.")
    finally:
        store.close()


# ── sync ─────────────────────────────────────────────────────────────


@cli.group()
def sync() -> None:
    """Sync doses across machines via a shared directory."""


def _require_sync_dir() -> Path:
    cfg = _get_config()
    sync_dir = cfg.get("sync_dir")
    if not sync_dir:
        raise click.ClickException(
            "Sync directory not configured. Run: hisspresso config set --sync-dir <path>"
        )
    return Path(str(sync_dir))


@sync.command(name="push")
def sync_push() -> None:
    """Export local changes to the sync directory."""
    from hisspresso.sync import push

    store = _get_store()
    cfg = _get_config()
    try:
        sync_dir = _require_sync_dir()
        machine_id = str(cfg["machine_id"])
        count = push(store, sync_dir, machine_id)
        if count:
            click.echo(f"Pushed {count} records.")
        else:
            click.echo("Nothing new to push.")
    finally:
        store.close()


@sync.command(name="pull")
def sync_pull() -> None:
    """Import remote changes from the sync directory."""
    from hisspresso.sync import pull

    store = _get_store()
    cfg = _get_config()
    try:
        sync_dir = _require_sync_dir()
        machine_id = str(cfg["machine_id"])
        inserted, updated = pull(store, sync_dir, machine_id)
        click.echo(f"Pulled {inserted} new, {updated} updated.")
    finally:
        store.close()


@sync.command(name="status")
def sync_status() -> None:
    """Show sync configuration and status."""
    store = _get_store()
    cfg = _get_config()
    try:
        sync_dir = cfg.get("sync_dir")
        click.echo(f"machine_id   : {cfg.get('machine_id', '?')}")
        click.echo(f"sync_dir     : {sync_dir or '(not set)'}")
        last_push = store.get_meta("last_push_at")
        click.echo(f"last_push_at : {last_push or '(never)'}")
    finally:
        store.close()
