"""Smoke test: CLI group loads and responds to --help."""

from click.testing import CliRunner

from hisspresso.cli import cli


def test_cli_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "hisspresso" in result.output
