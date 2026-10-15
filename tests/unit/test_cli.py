"""Smoke tests for the whyline CLI entry point."""

from typer.testing import CliRunner

from whyline import __version__
from whyline.cli import app

runner = CliRunner()


def test_version_prints_package_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_unknown_command_fails() -> None:
    result = runner.invoke(app, ["no-such-command"])
    assert result.exit_code != 0
