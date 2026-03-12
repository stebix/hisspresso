"""Tests for cli.py — Phase 3."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from hisspresso.cli import _parse_at, cli

# ── _parse_at ────────────────────────────────────────────────────────


def test_parse_at_none_returns_utc_now() -> None:
    result = _parse_at(None)
    assert "+00:00" in result or "Z" in result


def test_parse_at_bare_time() -> None:
    result = _parse_at("14:30")
    # Should be a valid ISO timestamp.
    from datetime import datetime

    dt = datetime.fromisoformat(result)
    assert dt.minute == 30


def test_parse_at_full_datetime() -> None:
    result = _parse_at("2026-03-09 21:00")
    from datetime import datetime

    dt = datetime.fromisoformat(result)
    assert dt.year == 2026
    assert dt.month == 3


def test_parse_at_invalid_raises() -> None:
    import click

    with pytest.raises(click.BadParameter):
        _parse_at("not-a-time")


# ── log command ──────────────────────────────────────────────────────


@pytest.fixture()
def _cli_env(tmp_path: Path) -> Iterator[None]:
    """Patch data paths so the CLI writes to a temp directory."""
    with (
        patch("hisspresso.cli._DATA_DIR", tmp_path),
        patch("hisspresso.cli._DB_PATH", tmp_path / "hisspresso.db"),
        patch("hisspresso.cli._CONFIG_PATH", tmp_path / "config.json"),
    ):
        yield


@pytest.mark.usefixtures("_cli_env")
def test_log_known_beverage() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["log", "coffee"])
    assert result.exit_code == 0
    assert "coffee" in result.output
    assert "95" in result.output


@pytest.mark.usefixtures("_cli_env")
def test_log_with_explicit_caffeine() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["log", "mystery-drink", "--caffeine", "120"])
    assert result.exit_code == 0
    assert "120" in result.output


@pytest.mark.usefixtures("_cli_env")
def test_log_with_count() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["log", "espresso", "--count", "2"])
    assert result.exit_code == 0
    assert "2×" in result.output
    assert "126" in result.output


@pytest.mark.usefixtures("_cli_env")
def test_log_unknown_beverage_no_caffeine() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["log", "unicorn-juice"])
    assert result.exit_code != 0
    assert "Unknown beverage" in result.output


@pytest.mark.usefixtures("_cli_env")
def test_log_with_at_flag() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["log", "coffee", "--at", "09:00"])
    assert result.exit_code == 0
    assert "coffee" in result.output


# ── undo / delete / restore ──────────────────────────────────────────


@pytest.mark.usefixtures("_cli_env")
def test_undo_after_log() -> None:
    runner = CliRunner()
    runner.invoke(cli, ["log", "coffee"])
    result = runner.invoke(cli, ["undo"])
    assert result.exit_code == 0
    assert "Undone" in result.output


@pytest.mark.usefixtures("_cli_env")
def test_undo_empty() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["undo"])
    assert result.exit_code == 0
    assert "Nothing to undo" in result.output


@pytest.mark.usefixtures("_cli_env")
def test_delete_and_restore() -> None:
    runner = CliRunner()
    log_result = runner.invoke(cli, ["log", "coffee"])
    # Extract short ID from output like "Logged 1× coffee (95 mg) [abcd1234]"
    short_id = log_result.output.strip().split("[")[1].rstrip("]")

    del_result = runner.invoke(cli, ["delete", short_id])
    assert del_result.exit_code == 0
    assert "Deleted" in del_result.output

    restore_result = runner.invoke(cli, ["restore", short_id])
    assert restore_result.exit_code == 0
    assert "Restored" in restore_result.output


@pytest.mark.usefixtures("_cli_env")
def test_delete_bad_id() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["delete", "zzz-no-match"])
    assert result.exit_code != 0


# ── list ─────────────────────────────────────────────────────────────


@pytest.mark.usefixtures("_cli_env")
def test_list_empty() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["list"])
    assert result.exit_code == 0
    assert "No entries" in result.output


@pytest.mark.usefixtures("_cli_env")
def test_list_after_log() -> None:
    runner = CliRunner()
    runner.invoke(cli, ["log", "coffee"])
    result = runner.invoke(cli, ["list"])
    assert result.exit_code == 0
    assert "coffee" in result.output


@pytest.mark.usefixtures("_cli_env")
def test_list_deleted_flag() -> None:
    runner = CliRunner()
    runner.invoke(cli, ["log", "coffee"])
    runner.invoke(cli, ["undo"])
    result = runner.invoke(cli, ["list", "--deleted"])
    assert result.exit_code == 0
    assert "coffee" in result.output
    assert "yes" in result.output


# ── beverages ────────────────────────────────────────────────────────


@pytest.mark.usefixtures("_cli_env")
def test_beverages_list() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["beverages"])
    assert result.exit_code == 0
    assert "espresso" in result.output
    assert "coffee" in result.output


@pytest.mark.usefixtures("_cli_env")
def test_beverages_add_and_remove() -> None:
    runner = CliRunner()
    add_result = runner.invoke(cli, ["beverages", "add", "oat latte", "--caffeine", "63"])
    assert add_result.exit_code == 0
    assert "oat-latte" in add_result.output

    # Should appear in list.
    list_result = runner.invoke(cli, ["beverages"])
    assert "oat-latte" in list_result.output

    remove_result = runner.invoke(cli, ["beverages", "remove", "oat latte"])
    assert remove_result.exit_code == 0
    assert "Removed" in remove_result.output


# ── config ───────────────────────────────────────────────────────────


@pytest.mark.usefixtures("_cli_env")
def test_config_show() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "show"])
    assert result.exit_code == 0
    assert "half_life_hours" in result.output


@pytest.mark.usefixtures("_cli_env")
def test_config_set_half_life() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "set", "--half-life", "9"])
    assert result.exit_code == 0
    assert "updated" in result.output.lower()

    show = runner.invoke(cli, ["config", "show"])
    assert "9" in show.output
