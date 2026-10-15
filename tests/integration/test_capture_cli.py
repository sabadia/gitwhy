"""``gitwhy capture`` (flags mode) against real git repositories (docs/03 section 4)."""

import json
import subprocess
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
import yaml
from typer.testing import CliRunner, Result

from gitwhy.cli import app
from gitwhy.errors import NoRepoError, UsageError
from gitwhy.gitio import staged_paths
from gitwhy.models import Record
from gitwhy.store import RecordStore, initialize
from tests.conftest import plain

runner = CliRunner()


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)  # noqa: S603, S607


def _stage(repo: Path, *names: str) -> None:
    for name in names:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"content of {name}\n", encoding="utf-8")
    _git(repo, "add", "--", *names)


def _capture(cwd: Path, monkeypatch: pytest.MonkeyPatch, *args: str) -> Result:
    monkeypatch.chdir(cwd)
    return runner.invoke(app, ["capture", *args])


@pytest.fixture
def repo(git_repo: Path) -> Path:
    initialize(git_repo)
    return git_repo


def _records(repo: Path) -> list[Record]:
    result = RecordStore(repo / ".gitwhy").list()
    assert result.errors == []
    return [Record.model_validate(r.model_dump()) for r in result.records]


def _json(result: Result) -> dict[str, Any]:
    data = json.loads(result.stdout)
    assert isinstance(data, dict)
    return data


# --- docs/05 required ---------------------------------------------------------------------


def test_capture_in_non_repo_exits_2_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plain_dir = tmp_path / "plain"
    plain_dir.mkdir()
    result = _capture(plain_dir, monkeypatch, "--goal", "g", "--file", "a.py")
    assert result.exit_code == 2
    assert list(plain_dir.iterdir()) == []


# --- happy paths -------------------------------------------------------------------------------


def test_every_flag_lands_in_the_record(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _capture(
        repo,
        monkeypatch,
        "--goal", "Close invoices at end of day",
        "--constraint", "No API change",
        "--constraint", "No new deps",
        "--rejected", "Per-request close",
        "--rejected-reason", "Breaks batch discount",
        "--rejected", "Cron",
        "--assumption", "Invoices mutable until close",
        "--falsifier", "Customer charged before close",
        "--risk", "No lock",
        "--file", "src/billing/close.py",
        "--file", "src/billing/models.py",
        "--evidence-test", "tests/test_close.py::test_daily_close",
        "--adr", "docs/decisions/0042.md",
        "--author-name", "Ada",
        "--json",
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    data = _json(result)
    (record,) = _records(repo)
    assert data["record"] == record.model_dump(mode="json")
    assert record.goal == "Close invoices at end of day"
    assert record.constraints == ["No API change", "No new deps"]
    assert [(r.option, r.reason) for r in record.rejected] == [
        ("Per-request close", "Breaks batch discount"),
        ("Cron", ""),
    ]
    assert record.assumptions == ["Invoices mutable until close"]
    assert record.falsifier == "Customer charged before close"
    assert record.risks == ["No lock"]
    assert record.evidence[0].ref == "tests/test_close.py::test_daily_close"
    assert record.adr == "docs/decisions/0042.md"
    assert record.author.name == "Ada" and record.author.kind == "human"
    assert [link.path for link in record.links] == ["src/billing/close.py", "src/billing/models.py"]
    assert record.status == "draft"
    assert record.source.kind == "flags"


def test_saved_file_is_a_valid_record(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _capture(repo, monkeypatch, "--goal", "g", "--file", "a.py", "--json")
    path = repo / _json(result)["path"]
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert Record.model_validate(data).goal == "g"


def test_minimal_capture_leaves_narrative_fields_empty(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _capture(repo, monkeypatch, "--goal", "g", "--file", "a.py")
    (record,) = _records(repo)
    assert record.rejected == [] and record.assumptions == [] and record.falsifier == ""
    assert record.constraints == [] and record.risks == [] and record.evidence == []


def test_default_links_are_staged_files(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stage(repo, "src/app.py", "docs/my notes.md", "naïve.txt")
    result = _capture(repo, monkeypatch, "--goal", "g")
    assert result.exit_code == 0, result.output
    (record,) = _records(repo)
    assert sorted(link.path for link in record.links) == [
        "docs/my notes.md",
        "naïve.txt",
        "src/app.py",
    ]


def test_staged_gitwhy_files_are_not_linked(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _git(repo, "add", ".gitwhy")
    _stage(repo, "a.py")
    assert staged_paths(repo) == ["a.py"]


def test_file_from_subdirectory_is_repo_relative(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sub = repo / "src" / "pkg"
    sub.mkdir(parents=True)
    result = _capture(
        sub, monkeypatch, "--goal", "g", "--file", "mod.py", "--file", "../../README.md"
    )
    assert result.exit_code == 0, result.output
    (record,) = _records(repo)
    assert [link.path for link in record.links] == ["src/pkg/mod.py", "README.md"]


def test_agent_tool_marks_agent_author(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _capture(repo, monkeypatch, "--goal", "g", "--file", "a.py", "--agent-tool", "claude-code")
    (record,) = _records(repo)
    assert (record.author.kind, record.author.tool) == ("agent", "claude-code")
    assert record.status == "draft"


def test_default_author_name_from_config(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (repo / ".gitwhy" / "config.yml").write_text(
        "capture:\n  default_author_name: Grace\n", encoding="utf-8"
    )
    _capture(repo, monkeypatch, "--goal", "first", "--file", "a.py")
    _capture(repo, monkeypatch, "--goal", "second", "--file", "a.py", "--author-name", "Ada")
    names = {r.goal: r.author.name for r in _records(repo)}
    assert names == {"first": "Grace", "second": "Ada"}


def test_pending_writes_only_the_id(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _capture(repo, monkeypatch, "--goal", "g", "--file", "a.py", "--pending")
    assert result.exit_code == 0, result.output
    (record,) = _records(repo)
    assert (repo / ".gitwhy" / "pending").read_text(encoding="utf-8") == f"{record.id}\n"
    assert "marked pending in .gitwhy/pending" in result.output


def test_without_pending_no_pending_file(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _capture(repo, monkeypatch, "--goal", "g", "--file", "a.py")
    assert not (repo / ".gitwhy" / "pending").exists()


def test_ids_are_unique_uuid7(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ids = {
        _json(_capture(repo, monkeypatch, "--goal", f"g{n}", "--file", "a.py", "--json"))["id"]
        for n in range(3)
    }
    assert len(ids) == 3
    assert all(UUID(i).version == 7 for i in ids)


def test_human_output(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _capture(repo, monkeypatch, "--goal", "g", "--file", "a.py")
    (record,) = _records(repo)
    assert result.stdout.splitlines() == [
        f"Captured draft {record.id}",
        f"  .gitwhy/records/{record.id}.yml",
    ]


def test_json_shape(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = _json(
        _capture(repo, monkeypatch, "--goal", "g", "--file", "a.py", "--pending", "--json")
    )
    assert set(data) == {"id", "path", "pending", "record"}
    assert data["path"] == f".gitwhy/records/{data['id']}.yml"
    assert data["pending"] is True
    assert data["record"]["id"] == data["id"]
    assert data["record"]["status"] == "draft"


# --- failure paths ---------------------------------------------------------------------------


def test_without_goal_exits_1(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _capture(repo, monkeypatch, "--file", "a.py")
    assert result.exit_code == 1
    assert "--goal" in plain(result.output)
    assert _records(repo) == []


def test_nothing_staged_and_no_file_exits_1(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _capture(repo, monkeypatch, "--goal", "g")
    assert result.exit_code == 1
    assert "Nothing is staged" in plain(result.output)
    assert _records(repo) == []


def test_file_outside_repo_exits_1(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _capture(repo, monkeypatch, "--goal", "g", "--file", "../elsewhere.py")
    assert result.exit_code == 1
    assert "outside the repository" in plain(result.output)


def test_extra_rejected_reason_exits_1(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _capture(
        repo, monkeypatch, "--goal", "g", "--file", "a.py", "--rejected-reason", "orphan"
    )
    assert result.exit_code == 1
    assert _records(repo) == []


def test_goal_too_long_exits_1(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _capture(repo, monkeypatch, "--goal", "x" * 501, "--file", "a.py")
    assert result.exit_code == 1


def test_not_initialized_exits_2(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _capture(git_repo, monkeypatch, "--goal", "g", "--file", "a.py")
    assert result.exit_code == 2
    assert "gitwhy init" in plain(result.output)
    assert not (git_repo / ".gitwhy").exists()


def test_corrupt_config_exits_4(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (repo / ".gitwhy" / "config.yml").write_text("chek: {}\n", encoding="utf-8")
    result = _capture(repo, monkeypatch, "--goal", "g", "--file", "a.py")
    assert result.exit_code == 4
    assert _records(repo) == []


def test_staged_paths_outside_repo_is_no_repo(tmp_path: Path) -> None:
    with pytest.raises(NoRepoError, match="Cannot list staged files"):
        staged_paths(tmp_path)


def test_staged_paths_with_non_utf8_names(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = subprocess.CompletedProcess(args=[], returncode=0, stdout=b"ok\0bad\xff\0", stderr=b"")
    monkeypatch.setattr("gitwhy.gitio.subprocess.run", lambda *a, **k: fake)
    with pytest.raises(UsageError, match="not valid UTF-8"):
        staged_paths(git_repo)


def test_help_lists_exit_codes() -> None:
    text = plain(runner.invoke(app, ["capture", "--help"]).stdout)
    assert "Exits 1" in text and "2 outside a git repository" in text


# --- capture --affirm (the human gate is shared with `gitwhy affirm`) ------------------------

FULL = (
    "--constraint", "c", "--rejected", "r", "--assumption", "a",
    "--falsifier", "f", "--risk", "k", "--evidence-test", "tests/t.py::t",
)  # fmt: skip


def _tty(monkeypatch: pytest.MonkeyPatch, value: bool) -> None:
    monkeypatch.setattr("gitwhy.cli.stdin_is_tty", lambda: value)


def test_capture_affirm_from_non_tty_exits_8_and_writes_nothing(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stage(repo, "a.py")
    result = _capture(repo, monkeypatch, "--goal", "g", "--affirm", "--pending")
    assert result.exit_code == 8, result.output
    assert "--i-am-human" in plain(result.output)
    assert _records(repo) == []
    assert not (repo / ".gitwhy" / "pending").exists()


def test_capture_affirm_gate_runs_before_anything_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plain_dir = tmp_path / "not-a-repo"
    plain_dir.mkdir()
    result = _capture(plain_dir, monkeypatch, "--affirm")
    assert result.exit_code == 8


def test_capture_affirm_with_i_am_human_on_non_tty(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stage(repo, "a.py")
    result = _capture(
        repo, monkeypatch, "--goal", "g", "--author-name", "Ada", "--affirm", "--i-am-human"
    )
    assert result.exit_code == 0, result.output
    (record,) = _records(repo)
    assert record.status == "affirmed"
    assert record.affirmed_by == "Ada"
    assert record.affirmed_at == record.created_at
    assert "Captured and affirmed" in plain(result.output)
    assert "Warning: affirmed with empty fields" in plain(result.output)
    assert record.rejected == [] and record.falsifier == ""


def test_capture_affirm_defaults_affirmer_to_git_user_name(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _git(repo, "config", "user.name", "Grace Hopper")
    _stage(repo, "a.py")
    result = _capture(repo, monkeypatch, "--goal", "g", "--affirm", "--i-am-human", *FULL)
    assert result.exit_code == 0, result.output
    (record,) = _records(repo)
    assert record.affirmed_by == "Grace Hopper"
    assert "Warning" not in plain(result.output)


def test_capture_affirm_without_any_name_exits_1_and_writes_nothing(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _git(repo, "config", "user.name", "")
    _stage(repo, "a.py")
    result = _capture(repo, monkeypatch, "--goal", "g", "--affirm", "--i-am-human")
    assert result.exit_code == 1, result.output
    assert _records(repo) == []


def test_capture_affirm_on_tty_confirms_empty_fields(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _tty(monkeypatch, True)
    _stage(repo, "a.py")
    monkeypatch.chdir(repo)
    result = runner.invoke(
        app, ["capture", "--goal", "g", "--author-name", "Ada", "--affirm"], input="y\n"
    )
    assert result.exit_code == 0, result.output
    assert "These fields are empty" in plain(result.output)
    (record,) = _records(repo)
    assert record.status == "affirmed"


def test_capture_affirm_declined_on_tty_writes_nothing(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _tty(monkeypatch, True)
    _stage(repo, "a.py")
    monkeypatch.chdir(repo)
    result = runner.invoke(
        app,
        ["capture", "--goal", "g", "--author-name", "Ada", "--affirm", "--pending"],
        input="n\n",
    )
    assert result.exit_code == 1, result.output
    assert "Not captured" in plain(result.output)
    assert _records(repo) == []
    assert not (repo / ".gitwhy" / "pending").exists()


def test_capture_affirm_yes_skips_the_question(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _tty(monkeypatch, True)
    _stage(repo, "a.py")
    result = _capture(repo, monkeypatch, "--goal", "g", "--author-name", "Ada", "--affirm", "--yes")
    assert result.exit_code == 0, result.output
    assert "These fields are empty" not in plain(result.output)
    assert _records(repo)[0].status == "affirmed"


def test_capture_affirm_json(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stage(repo, "a.py")
    result = _capture(
        repo, monkeypatch, "--goal", "g", "--author-name", "Ada", "--affirm", "--i-am-human",
        "--json", *FULL,
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    assert _json(result)["record"]["status"] == "affirmed"


def test_yes_and_i_am_human_without_affirm_still_draft(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stage(repo, "a.py")
    result = _capture(repo, monkeypatch, "--goal", "g", "--yes", "--i-am-human")
    assert result.exit_code == 0, result.output
    assert _records(repo)[0].status == "draft"
