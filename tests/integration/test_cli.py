"""CLI behaviour: entry point, help, and the exit code contract (docs/03 section 3)."""

import io
import json
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from intentline import __version__
from intentline.cli import IntentlineGroup, app, emit_json, open_store, stdin_is_tty
from intentline.errors import (
    AffirmRefusedError,
    CorruptError,
    ExitCode,
    IntentlineError,
    NoRepoError,
    NotFoundError,
    SchemaVersionError,
)
from tests.conftest import plain

runner = CliRunner()


def test_version_prints_package_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_root_help_documents_every_exit_code() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    text = plain(result.stdout)
    for code in ExitCode:
        assert f"{int(code)} " in text
    assert "9 not found" in text


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["no-such-command"],
        ["--no-such-option"],
        ["version", "--no-such-option"],
        ["schema", "extra-argument"],
    ],
)
def test_usage_errors_exit_1_not_2(args: list[str]) -> None:
    result = runner.invoke(app, args)
    assert result.exit_code == 1, result.output


# --- IntentlineError mapping, exercised through a throwaway app on the same group class ------

probe = typer.Typer(cls=IntentlineGroup)


@probe.callback()
def _probe_root() -> None:
    """Probe app."""


@probe.command()
def fail(kind: str) -> None:
    """Raise the named intentline error."""
    errors: dict[str, IntentlineError] = {
        "no-repo": NoRepoError("Not a git repository: /tmp/x.", hint="Run inside a repo."),
        "corrupt": CorruptError("Record 0193 failed validation (.intentline/records/0193.yml)."),
        "schema": SchemaVersionError("Record uses schema version 9."),
        "affirm": AffirmRefusedError("Refusing to affirm from a non-interactive shell."),
        "missing": NotFoundError("No record with id 0193.", hint="Run `intentline list`."),
    }
    raise errors[kind]


@probe.command()
def needs(name: str) -> None:
    """Require one argument."""


@pytest.mark.parametrize(
    ("kind", "code"),
    [
        ("no-repo", ExitCode.NO_REPO),
        ("corrupt", ExitCode.CORRUPT),
        ("schema", ExitCode.SCHEMA),
        ("affirm", ExitCode.AFFIRM_REFUSED),
        ("missing", ExitCode.NOT_FOUND),
    ],
)
def test_intentline_errors_keep_their_exit_code(kind: str, code: ExitCode) -> None:
    result = runner.invoke(probe, ["fail", kind])
    assert result.exit_code == code


def test_intentline_error_message_and_hint_go_to_stderr() -> None:
    result = runner.invoke(probe, ["fail", "missing"])
    assert result.stdout == ""
    stderr = plain(result.stderr)
    assert "No record with id 0193." in stderr
    assert "Run `intentline list`." in stderr


def test_missing_argument_is_usage_error() -> None:
    result = runner.invoke(probe, ["needs"])
    assert result.exit_code == ExitCode.USAGE


def test_exit_code_2_is_reserved_for_no_repo() -> None:
    usage = runner.invoke(probe, ["needs"])
    no_repo = runner.invoke(probe, ["fail", "no-repo"])
    assert usage.exit_code != 2
    assert no_repo.exit_code == 2


# --- shared command plumbing -------------------------------------------------------------------


def test_open_store_uses_repo_root(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sub = git_repo / "deep"
    sub.mkdir()
    monkeypatch.chdir(sub)
    root, store = open_store()
    assert root == git_repo
    assert store.intentline_dir == git_repo / ".intentline"


def test_emit_json_writes_one_document(capsys: pytest.CaptureFixture[str]) -> None:
    emit_json({"goal": "café", "n": [1]})
    assert json.loads(capsys.readouterr().out) == {"goal": "café", "n": [1]}


def test_stdin_is_tty_reflects_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert stdin_is_tty() is False
