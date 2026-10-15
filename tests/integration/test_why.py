"""``whyline why`` against real git histories (docs/02 section 4.4, docs/03 sections 4 and 7)."""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner, Result

from tests.conftest import plain, record_data, uuid7
from whyline.cli import app
from whyline.models import Record
from whyline.render import BANNER_AFFIRMED, BANNER_DRAFT
from whyline.store import RecordStore, initialize

runner = CliRunner()


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(  # noqa: S603
        ["git", "-C", str(repo), *args],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _commit(repo: Path, lines: list[str], message: str) -> str:
    (repo / "app.py").write_text("\n".join(lines) + "\n", encoding="utf-8")
    _git(repo, "add", "app.py")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _save(repo: Path, n: int, **overrides: Any) -> Record:
    record = Record.model_validate(record_data(n, **overrides))
    RecordStore(repo / ".whyline").save(record)
    return record


def _affirmed(n: int, **overrides: Any) -> dict[str, Any]:
    return {
        "status": "affirmed",
        "affirmed_at": record_data(n)["created_at"],
        "affirmed_by": "Reviewer",
        **overrides,
    }


@pytest.fixture
def repo(git_repo: Path) -> Path:
    _git(git_repo, "config", "user.name", "Test Human")
    _git(git_repo, "config", "user.email", "test@example.com")
    _git(git_repo, "config", "commit.gpgsign", "false")
    initialize(git_repo)
    return git_repo


@pytest.fixture
def history(repo: Path) -> dict[str, str]:
    """Three commits that each change line 2 of app.py, linked to records 1, 2, and 3."""
    _save(repo, 1, goal="First version of line two")
    _save(repo, 2, goal="Second version of line two")
    _save(repo, 3, goal="Third version of line two")
    shas = {
        "c1": _commit(repo, ["a", "one", "c"], f"one\n\nWhyline-Id: {uuid7(1)}"),
        "c2": _commit(repo, ["a", "two", "c"], f"two\n\nWhyline-Id: {uuid7(2)}"),
        "c3": _commit(repo, ["a", "three", "c"], f"three\n\nWhyline-Id: {uuid7(3)}"),
    }
    return shas


def _why(repo: Path, monkeypatch: pytest.MonkeyPatch, *args: str) -> Result:
    monkeypatch.chdir(repo)
    return runner.invoke(app, ["why", *args])


def _json(result: Result) -> dict[str, Any]:
    data = json.loads(result.stdout)
    assert isinstance(data, dict)
    return data


# --- docs/04 acceptance: temp repo with two commits ----------------------------------------------


def test_two_commits_drafts_newest_first(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _save(repo, 1, goal="Line two exists")
    _save(repo, 2, goal="Line two was changed")
    c1 = _commit(repo, ["a", "one", "c"], f"one\n\nWhyline-Id: {uuid7(1)}")
    c2 = _commit(repo, ["a", "two", "c"], f"two\n\nWhyline-Id: {uuid7(2)}")
    result = _why(repo, monkeypatch, "app.py:2")
    assert result.exit_code == 0, result.output
    text = result.stdout
    assert text.count(BANNER_DRAFT) == 2
    assert text.index("Line two was changed") < text.index("Line two exists")
    assert f"commit: {c2[:12]}" in text and f"commit: {c1[:12]}" in text
    assert text.startswith(BANNER_DRAFT)


def test_line_untouched_by_second_commit_shows_only_first(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _save(repo, 1, goal="Line one")
    _save(repo, 2, goal="Only line two")
    _commit(repo, ["a", "one", "c"], f"one\n\nWhyline-Id: {uuid7(1)}")
    _commit(repo, ["a", "two", "c"], f"two\n\nWhyline-Id: {uuid7(2)}")
    result = _why(repo, monkeypatch, "app.py:1")
    assert "Line one" in result.stdout
    assert "Only line two" not in result.stdout


# --- stop rule ----------------------------------------------------------------------------------


def test_stops_at_first_affirmed_but_shows_newer_drafts(
    repo: Path, history: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _save(repo, 2, goal="Second version of line two", **_affirmed(2))
    result = _why(repo, monkeypatch, "app.py:2")
    text = result.stdout
    assert "Third version" in text  # newer draft is shown
    assert "Second version" in text  # the affirmed one
    assert "First version" not in text  # older, hidden behind the affirmed record
    assert text.index(BANNER_DRAFT) < text.index(BANNER_AFFIRMED)
    assert "1 older record hidden behind the affirmed one; use --all." in plain(text)


def test_all_shows_records_behind_the_affirmed_one(
    repo: Path, history: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _save(repo, 2, goal="Second version of line two", **_affirmed(2))
    result = _why(repo, monkeypatch, "app.py:2", "--all")
    assert "First version" in result.stdout
    assert "hidden" not in result.stdout


def test_affirmed_newest_shows_only_it(
    repo: Path, history: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _save(repo, 3, goal="Third version of line two", **_affirmed(3))
    result = _why(repo, monkeypatch, "app.py:2")
    assert result.stdout.startswith(BANNER_AFFIRMED)
    assert BANNER_DRAFT not in result.stdout
    assert "2 older records hidden" in plain(result.stdout)


# --- --commit ---------------------------------------------------------------------------------


def test_commit_lookup(
    repo: Path, history: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _why(repo, monkeypatch, "--commit", history["c2"][:7])
    assert result.exit_code == 0, result.output
    assert "Second version" in result.stdout
    assert "Third version" not in result.stdout
    assert f"commit: {history['c2'][:12]}" in result.stdout


def test_commit_without_trailer(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sha = _commit(repo, ["x"], "no trailer")
    result = _why(repo, monkeypatch, "--commit", sha)
    assert result.exit_code == 0
    assert f"No record explains commit {sha}." in plain(result.stdout)


def test_unknown_commit_exits_9(
    repo: Path, history: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _why(repo, monkeypatch, "--commit", "deadbeef")
    assert result.exit_code == 9


def test_commit_json(repo: Path, history: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    data = _json(_why(repo, monkeypatch, "--commit", history["c1"], "--json"))
    assert data["query"] == {"commit": history["c1"]}
    (entry,) = data["records"]
    assert entry["record"]["id"] == str(uuid7(1))
    assert entry["resolved_commits"] == [history["c1"]]


# --- links without a trailer ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("start", "end", "line", "expected"),
    [
        (None, None, 7, True),  # whole file
        (5, 9, 7, True),
        (5, 9, 9, True),
        (5, 9, 10, False),
        (7, None, 7, True),  # single line given as start only
        (None, 7, 7, True),
        (7, None, 8, False),
    ],
)
def test_record_linked_by_path_and_range(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    start: int | None,
    end: int | None,
    line: int,
    expected: bool,
) -> None:
    _save(
        repo,
        1,
        goal="Pending reason",
        links=[{"path": "app.py", "start_line": start, "end_line": end}],
    )
    result = _why(repo, monkeypatch, f"app.py:{line}", "--json")
    data = _json(result)
    assert (len(data["records"]) == 1) is expected
    if expected:
        assert data["records"][0]["via_link"] is True
        assert data["records"][0]["resolved_commits"] == []


def test_link_on_another_path_does_not_match(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _save(repo, 1, links=[{"path": "other.py", "start_line": None, "end_line": None}])
    _commit(repo, ["a"], "no trailer")
    assert "No record explains app.py:1." in plain(_why(repo, monkeypatch, "app.py:1").stdout)


def test_record_linked_from_two_commits_is_listed_once_with_both(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _save(repo, 1, goal="One reason, two commits")
    c1 = _commit(repo, ["a", "one"], f"one\n\nWhyline-Id: {uuid7(1)}")
    c2 = _commit(repo, ["a", "two"], f"follow-up fix\n\nWhyline-Id: {uuid7(1)}")
    data = _json(_why(repo, monkeypatch, "app.py:2", "--json"))
    (entry,) = data["records"]
    assert entry["resolved_commits"] == [c2, c1]
    text = _why(repo, monkeypatch, "app.py:2").stdout
    assert text.count("One reason, two commits") == 1
    assert f"commit: {c2[:12]}" in text


def test_record_found_by_trailer_and_link_is_listed_once(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _save(repo, 1, links=[{"path": "app.py", "start_line": 1, "end_line": 3}])
    sha = _commit(repo, ["a", "b", "c"], f"one\n\nWhyline-Id: {uuid7(1)}")
    data = _json(_why(repo, monkeypatch, "app.py:2", "--json"))
    (entry,) = data["records"]
    assert entry["via_link"] is False
    assert entry["resolved_commits"] == [sha]


# --- empty, missing, broken -----------------------------------------------------------------------


def test_unknown_file_is_empty_with_exit_0(
    repo: Path, history: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _why(repo, monkeypatch, "nope.py:3")
    assert result.exit_code == 0
    assert "No record explains nope.py:3." in plain(result.stdout)


def test_line_past_end_of_file_is_empty(
    repo: Path, history: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _why(repo, monkeypatch, "app.py:99")
    assert result.exit_code == 0
    assert "No record explains" in result.stdout


def test_empty_repository(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _why(repo, monkeypatch, "app.py:1")
    assert result.exit_code == 0
    assert "No commits yet, and no record explains app.py:1." in plain(result.stdout)


def test_trailer_without_record_file_warns_and_continues(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _save(repo, 1, goal="Still here")
    _commit(repo, ["a", "one"], f"one\n\nWhyline-Id: {uuid7(1)}")
    _commit(repo, ["a", "two"], f"two\n\nWhyline-Id: {uuid7(9)}")
    result = _why(repo, monkeypatch, "app.py:2")
    assert result.exit_code == 0
    assert f"record missing for id {uuid7(9)}" in plain(result.stderr)
    assert "Still here" in result.stdout
    assert _json(_why(repo, monkeypatch, "app.py:2", "--json"))["missing"] == [str(uuid7(9))]


def test_corrupt_record_warns_and_others_still_show(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _save(repo, 1, goal="Good one")
    (repo / ".whyline" / "records" / f"{uuid7(2)}.yml").write_text("[broken\n", encoding="utf-8")
    _commit(repo, ["a"], f"one\n\nWhyline-Id: {uuid7(1)}\nWhyline-Id: {uuid7(2)}")
    result = _why(repo, monkeypatch, "app.py:1")
    assert result.exit_code == 0
    assert "Good one" in result.stdout
    assert "not valid YAML" in plain(result.stderr)


@pytest.mark.parametrize(("depth", "found"), [(1, False), (2, True)])
def test_shallow_clone_prints_a_hint(
    repo: Path,
    history: dict[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    depth: int,
    found: bool,
) -> None:
    """docs/05: a shallow clone may miss older records, so ``why`` prints a hint."""
    _git(repo, "add", ".whyline")
    _git(repo, "commit", "-q", "-m", "Commit the records, as a real project does")
    clone = tmp_path / "shallow"
    subprocess.run(  # noqa: S603
        ["git", "clone", "-q", "--depth", str(depth), f"file://{repo}", str(clone)],  # noqa: S607
        check=True,
        capture_output=True,
    )
    result = _why(clone, monkeypatch, "app.py:2")
    assert result.exit_code == 0
    assert "shallow clone" in plain(result.stderr)
    assert ("Third version" in result.stdout) is found


# --- input handling -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["app.py"],
        ["app.py:x"],
        ["app.py:0"],
        [":3"],
        ["app.py:2", "--commit", "HEAD"],
        ["../out.py:1"],
    ],
)
def test_bad_input_exits_1(repo: Path, monkeypatch: pytest.MonkeyPatch, args: list[str]) -> None:
    assert _why(repo, monkeypatch, *args).exit_code == 1


def test_path_relative_to_subdirectory(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (repo / "pkg").mkdir()
    _save(
        repo, 1, goal="Nested", links=[{"path": "pkg/mod.py", "start_line": None, "end_line": None}]
    )
    result = _why(repo / "pkg", monkeypatch, "mod.py:1")
    assert "Nested" in result.stdout


def test_not_initialized_exits_2(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert _why(git_repo, monkeypatch, "app.py:1").exit_code == 2
    assert _why(git_repo, monkeypatch, "--commit", "HEAD").exit_code == 2


def test_line_json_shape(
    repo: Path, history: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    data = _json(_why(repo, monkeypatch, "app.py:2", "--json"))
    assert data["query"] == {"path": "app.py", "line": 2}
    assert [e["record"]["id"] for e in data["records"]] == [str(uuid7(n)) for n in (3, 2, 1)]
    assert data["hidden"] == 0 and data["missing"] == []
    assert "DRAFT" not in json.dumps(data)


# --- end to end: capture, link, hook, commit, why ---------------------------------------------


def test_capture_pending_commit_through_hook_then_why(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(repo)
    (repo / "app.py").write_text("def close():\n    return 'daily'\n", encoding="utf-8")
    _git(repo, "add", "app.py")
    assert runner.invoke(app, ["install-hooks"]).exit_code == 0
    captured = runner.invoke(
        app, ["capture", "--goal", "Close invoices daily", "--pending", "--json"]
    )
    assert captured.exit_code == 0, captured.output
    record_id = json.loads(captured.stdout)["id"]
    env = {**os.environ, "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"]}
    subprocess.run(  # noqa: S603
        ["git", "-C", str(repo), "commit", "-q", "-m", "Close invoices daily"],  # noqa: S607
        check=True,
        capture_output=True,
        env=env,
    )
    result = runner.invoke(app, ["why", "app.py:2"])
    assert result.exit_code == 0, result.output
    assert result.stdout.startswith(BANNER_DRAFT)
    assert f"id: {record_id}" in result.stdout
    assert f"commit: {_git(repo, 'rev-parse', 'HEAD')[:12]}" in result.stdout
