"""README quickstart and man-quality --help (docs/05 section 6, docs/06 section 6)."""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from typer.main import get_command
from typer.testing import CliRunner

from tests.conftest import plain
from whyline.cli import app

runner = CliRunner()
ROOT = Path(__file__).resolve().parents[2]
README = (ROOT / "README.md").read_text(encoding="utf-8")
VENV_BIN = str(Path(sys.executable).parent)

_REQUIRED = (
    "pre-release, MVP in progress",
    "git+https://github.com/sabadia/whyline",
    "uv tool install whyline",
    "whyline init",
    "whyline capture",
    "whyline link",
    "git add .whyline",
    "git commit",
    "whyline why",
    "docs/01-product-spec.md",
    "Apache",
    "No invented why",
    "remote-tracking",
    "abort",
    "shallow",
    "secrets",
    "Exit codes",
)


def _documents_exit(text: str) -> bool:
    """True when rendered help names an exit code.

    A command page that only lists flags, with no exit sentence, fails this check.
    """
    return "exit" in text.lower()


def _command_paths() -> list[tuple[str, ...]]:
    """Every command path, including hidden groups.

    Typer ships its own click, so the group is detected by a ``commands`` dict
    rather than ``isinstance(..., click.Group)``.
    """

    def walk(command: object, prefix: tuple[str, ...]) -> list[tuple[str, ...]]:
        raw = getattr(command, "commands", None)
        if not isinstance(raw, dict):
            return []
        found: list[tuple[str, ...]] = []
        for name, child in raw.items():
            if not isinstance(name, str):
                continue
            path = (*prefix, name)
            found.append(path)
            found.extend(walk(child, path))
        return found

    return [(), *walk(get_command(app), ())]


def _quickstart_body(text: str) -> str:
    start = text.index("## Quickstart\n") + len("## Quickstart\n")
    rest = text[start:]
    return rest[: rest.index("\n## ")]


def _git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(  # noqa: S603
        ["git", "-C", str(repo), *args],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return completed.stdout.strip()


def test_help_that_omits_exit_codes_fails_the_check() -> None:
    assert not _documents_exit("Print the installed whyline version.\n\n--help  Show this message.")


def test_every_command_help_names_exit_codes() -> None:
    paths = _command_paths()
    for required in (
        ("version",),
        ("schema",),
        ("adapters",),
        ("hook",),
        ("hook", "prepare-commit-msg"),
        ("hook", "pre-commit"),
    ):
        assert required in paths
    for path in paths:
        result = runner.invoke(app, [*path, "--help"])
        assert result.exit_code == 0, result.output
        text = plain(result.stdout)
        assert _documents_exit(text), path
        assert "--help" in text


def test_readme_has_install_quickstart_limits_and_a_short_quickstart() -> None:
    for snippet in _REQUIRED:
        assert snippet in README
    assert "not on PyPI yet" in README
    body = _quickstart_body(README)
    assert len(body.splitlines()) <= 30
    for step in (
        "whyline init",
        "whyline install-hooks",
        "whyline capture",
        "whyline link",
        "git add .whyline",
        "git commit",
        "whyline why",
    ):
        assert step in body


def test_readme_quickstart_links_a_commit_and_why_prints_the_goal(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _git(git_repo, "config", "user.name", "Test Human")
    _git(git_repo, "config", "user.email", "test@example.com")
    _git(git_repo, "config", "commit.gpgsign", "false")
    monkeypatch.chdir(git_repo)

    assert runner.invoke(app, ["init"]).exit_code == 0
    assert runner.invoke(app, ["install-hooks"]).exit_code == 0
    (git_repo / "src").mkdir()
    (git_repo / "src" / "app.py").write_text('print("close invoices")\n', encoding="utf-8")
    _git(git_repo, "add", "src/app.py")

    captured = runner.invoke(app, ["capture", "--goal", "Close invoices once a day."])
    assert captured.exit_code == 0, captured.output
    match = re.search(r"Captured draft (\S+)", plain(captured.stdout))
    assert match is not None
    record_id = match.group(1)

    linked = runner.invoke(app, ["link", record_id])
    assert linked.exit_code == 0, linked.output
    _git(git_repo, "add", ".whyline")
    env = {**os.environ, "PATH": VENV_BIN + os.pathsep + os.environ["PATH"]}
    commit = subprocess.run(  # noqa: S603
        ["git", "-C", str(git_repo), "commit", "-q", "-m", "feat: close invoices once a day"],  # noqa: S607
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert commit.returncode == 0, commit.stderr
    message = _git(git_repo, "log", "-1", "--format=%B")
    assert f"Whyline-Id: {record_id}" in message

    result = runner.invoke(app, ["why", "src/app.py:1"])
    assert result.exit_code == 0, result.output
    assert "Close invoices once a day." in result.stdout
