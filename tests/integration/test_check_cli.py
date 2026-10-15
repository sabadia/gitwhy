"""``whyline check`` against real git repositories (docs/03 section 4, docs/05 section 2)."""

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from tests.conftest import plain, uuid7
from whyline.check import CAPTURE_COMMAND
from whyline.cli import app
from whyline.errors import UsageError
from whyline.gitio import range_record_ids
from whyline.store import initialize, write_pending

runner = CliRunner()


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(  # noqa: S603
        ["git", "-C", str(repo), *args],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _stage(repo: Path, name: str, lines: int) -> None:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"line {i}\n" for i in range(lines)), encoding="utf-8")
    _git(repo, "add", "--", name)


def _commit(repo: Path, message: str) -> str:
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(git_repo: Path) -> Path:
    _git(git_repo, "config", "user.name", "Test Human")
    _git(git_repo, "config", "user.email", "test@example.com")
    _git(git_repo, "config", "commit.gpgsign", "false")
    initialize(git_repo)
    _stage(git_repo, "README.md", 1)
    _git(git_repo, "add", ".whyline")
    _commit(git_repo, "base")
    return git_repo


def _check(repo: Path, monkeypatch: pytest.MonkeyPatch, *args: str) -> Result:
    monkeypatch.chdir(repo)
    return runner.invoke(app, ["check", *args])


# --- docs/05 required ------------------------------------------------------------------------


def test_under_min_lines_exits_0(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stage(repo, "small.py", 10)
    result = _check(repo, monkeypatch)
    assert result.exit_code == 0, result.output
    assert "OK: 10 changed lines in staged changes, under the 30-line threshold." in plain(
        result.stdout
    )


def test_over_min_lines_without_record_exits_3(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stage(repo, "big.py", 40)
    result = _check(repo, monkeypatch)
    assert result.exit_code == 3, result.output
    message = plain(result.stderr)
    assert "40 changed lines in 1 file" in message
    assert CAPTURE_COMMAND in message


def test_over_min_lines_with_pending_id_exits_0(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stage(repo, "big.py", 40)
    write_pending(repo / ".whyline", uuid7(1))
    result = _check(repo, monkeypatch)
    assert result.exit_code == 0, result.output
    assert f"linked to record {uuid7(1)}" in plain(result.stdout)


# --- acceptance: ignored files, linked records -------------------------------------------------


def test_ignored_files_exit_0(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stage(repo, "uv.lock", 500)
    _stage(repo, "web/package-lock.json", 500)
    _stage(repo, "src/app.py", 5)
    result = _check(repo, monkeypatch, "--json")
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["changed_lines"] == 5
    assert sorted(data["ignored"]) == ["uv.lock", "web/package-lock.json"]


def test_head_with_trailer_counts_as_linked(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stage(repo, "a.py", 1)
    _commit(repo, f"linked\n\nWhyline-Id: {uuid7(2)}")
    _stage(repo, "big.py", 40)
    result = _check(repo, monkeypatch)
    assert result.exit_code == 0
    assert f"linked to record {uuid7(2)}" in plain(result.stdout)


def test_range_with_a_linked_commit_exits_0(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = _git(repo, "rev-parse", "HEAD")
    _stage(repo, "big.py", 40)
    _commit(repo, f"big\n\nWhyline-Id: {uuid7(3)}")
    _stage(repo, "more.py", 40)
    _commit(repo, "more, no trailer")
    result = _check(repo, monkeypatch, "--range", f"{base}..HEAD")
    assert result.exit_code == 0, result.output
    assert "80 changed lines" in plain(result.stdout)


def test_range_without_a_linked_commit_exits_3(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = _git(repo, "rev-parse", "HEAD")
    _stage(repo, "big.py", 40)
    _commit(repo, "no trailer")
    result = _check(repo, monkeypatch, "--range", f"{base}..HEAD")
    assert result.exit_code == 3
    assert f"({base}..HEAD)" in "".join(plain(result.stderr).split())  # Rich may wrap the sha


def test_range_record_ids_reports_a_bad_range(repo: Path) -> None:
    with pytest.raises(UsageError, match=r"git log failed for nope\.\.HEAD"):
        range_record_ids(repo, "nope..HEAD")


# --- options and config ----------------------------------------------------------------------


def test_min_lines_flag_overrides_config(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stage(repo, "small.py", 10)
    assert _check(repo, monkeypatch, "--min-lines", "5").exit_code == 3
    assert _check(repo, monkeypatch, "--min-lines", "11").exit_code == 0


def test_project_config_threshold(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (repo / ".whyline" / "config.yml").write_text("check:\n  min_lines: 100\n", encoding="utf-8")
    _stage(repo, "big.py", 40)
    assert _check(repo, monkeypatch).exit_code == 0


def test_project_config_ignore_list(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (repo / ".whyline" / "config.yml").write_text(
        "check:\n  ignore: ['vendor/**']\n", encoding="utf-8"
    )
    _stage(repo, "vendor/lib.py", 400)
    _stage(repo, "uv.lock", 400)  # no longer ignored: the project list replaced the default
    result = _check(repo, monkeypatch, "--json")
    assert result.exit_code == 3
    assert json.loads(result.stdout)["ignored"] == ["vendor/lib.py"]


@pytest.mark.parametrize(
    "args", [["--range", "HEAD"], ["--range", "nope..HEAD"], ["--min-lines", "-1"]]
)
def test_bad_options_exit_1(repo: Path, monkeypatch: pytest.MonkeyPatch, args: list[str]) -> None:
    assert _check(repo, monkeypatch, *args).exit_code == 1


def test_not_initialized_exits_2(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert _check(git_repo, monkeypatch).exit_code == 2


def test_outside_repo_exits_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plain_dir = tmp_path / "plain"
    plain_dir.mkdir()
    assert _check(plain_dir, monkeypatch).exit_code == 2


# --- robustness --------------------------------------------------------------------------------


def test_check_never_modifies_the_repository(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stage(repo, "big.py", 40)
    (repo / "untracked.txt").write_text("x\n", encoding="utf-8")
    before = (_git(repo, "status", "--porcelain=v1"), _git(repo, "rev-parse", "HEAD"))
    index_before = (repo / ".git" / "index").read_bytes()
    _check(repo, monkeypatch)
    _check(repo, monkeypatch, "--json")
    assert (_git(repo, "status", "--porcelain=v1"), _git(repo, "rev-parse", "HEAD")) == before
    assert (repo / ".git" / "index").read_bytes() == index_before
    assert not (repo / ".whyline" / "pending").exists()


def test_binary_and_renamed_files(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stage(repo, "old name.py", 40)
    _commit(repo, "add")
    _git(repo, "mv", "old name.py", "new name.py")
    (repo / "image.bin").write_bytes(b"\x00\x01\x02" * 100)
    _git(repo, "add", "image.bin")
    result = _check(repo, monkeypatch, "--json")
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["changed_lines"] == 0
    assert sorted(data["files"]) == ["image.bin", "new name.py"]


def test_first_commit_in_an_empty_repo(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    initialize(git_repo)
    _stage(git_repo, "big.py", 40)
    assert _check(git_repo, monkeypatch).exit_code == 3


def test_failure_json_still_exits_3(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stage(repo, "big.py", 40)
    result = _check(repo, monkeypatch, "--json")
    assert result.exit_code == 3
    data = json.loads(result.stdout)
    assert data == {
        "ok": False,
        "verdict": "needs_record",
        "scope": "staged changes",
        "changed_lines": 40,
        "min_lines": 30,
        "files": ["big.py"],
        "ignored": [],
        "linked_ids": [],
    }
