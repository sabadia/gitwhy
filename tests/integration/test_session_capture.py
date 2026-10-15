"""``whyline capture --session`` against real git repositories (docs/03 section 4, docs/05)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from tests.conftest import plain
from whyline.cli import app
from whyline.models import Record
from whyline.store import RecordStore, initialize

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "sessions"
NARRATIVE = ("constraints", "rejected", "assumptions", "evidence", "risks")

runner = CliRunner()


@pytest.fixture
def repo(git_repo: Path) -> Path:
    initialize(git_repo)
    return git_repo


def _stage(repo: Path, *names: str) -> None:
    for name in names:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"content of {name}\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "--", *names], check=True)  # noqa: S603, S607


def _capture(cwd: Path, monkeypatch: pytest.MonkeyPatch, *args: str) -> Result:
    monkeypatch.chdir(cwd)
    return runner.invoke(app, ["capture", *args])


def _records(repo: Path) -> list[Record]:
    result = RecordStore(repo / ".whyline").list()
    assert result.errors == []
    return [Record.model_validate(r.model_dump()) for r in result.records]


def _outside_copy(tmp_path: Path, name: str) -> Path:
    target = tmp_path / "home" / ".claude" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURES / name, target)
    return target


# --- docs/05 required: tempting prose never becomes a reason -----------------------------------


@pytest.mark.parametrize("name", ["messages.json", "array.json", "claude.jsonl", "plain.txt"])
def test_session_prose_never_fills_narrative_fields(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    _stage(repo, "src/billing/close.py")
    result = _capture(repo, monkeypatch, "--session", str(_outside_copy(tmp_path, name)))
    assert result.exit_code == 0, result.output
    (record,) = _records(repo)
    for field in NARRATIVE:
        assert getattr(record, field) == [], field
    assert record.falsifier == ""
    assert record.status == "draft"
    assert record.source.kind == "session"


def test_session_text_is_not_copied_into_the_record(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stage(repo, "src/billing/close.py")
    result = _capture(repo, monkeypatch, "--session", str(_outside_copy(tmp_path, "messages.json")))
    assert result.exit_code == 0, result.output
    saved = next((repo / ".whyline" / "records").glob("*.yml")).read_text(encoding="utf-8")
    for phrase in ("Redis", "mutable", "charged early", "API shape", "discounts", "agent"):
        assert phrase not in saved
    assert "goal: Close invoices at end of day, not per request." in saved


# --- goal and files -----------------------------------------------------------------------------


def test_goal_comes_from_first_user_message(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stage(repo, "a.py")
    result = _capture(repo, monkeypatch, "--session", str(_outside_copy(tmp_path, "claude.jsonl")))
    assert result.exit_code == 0, result.output
    assert _records(repo)[0].goal == "Make the daily close idempotent"


def test_goal_flag_overrides_session(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stage(repo, "a.py")
    session = _outside_copy(tmp_path, "plain.txt")
    result = _capture(repo, monkeypatch, "--session", str(session), "--goal", "Typed by a human")
    assert result.exit_code == 0, result.output
    record = _records(repo)[0]
    assert record.goal == "Typed by a human"
    assert record.source.kind == "session"


def test_session_files_link_the_record(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stage(repo, "unrelated.py")
    result = _capture(repo, monkeypatch, "--session", str(_outside_copy(tmp_path, "messages.json")))
    assert result.exit_code == 0, result.output
    assert [link.path for link in _records(repo)[0].links] == ["src/billing/close.py"]


def test_file_flag_overrides_session_files(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _outside_copy(tmp_path, "messages.json")
    result = _capture(repo, monkeypatch, "--session", str(session), "--file", "other.py")
    assert result.exit_code == 0, result.output
    assert [link.path for link in _records(repo)[0].links] == ["other.py"]


def test_session_without_files_falls_back_to_staged(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stage(repo, "staged.py")
    result = _capture(repo, monkeypatch, "--session", str(_outside_copy(tmp_path, "plain.txt")))
    assert result.exit_code == 0, result.output
    assert [link.path for link in _records(repo)[0].links] == ["staged.py"]


def test_session_files_resolve_from_a_subdirectory(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sub = repo / "deep" / "er"
    sub.mkdir(parents=True)
    result = _capture(sub, monkeypatch, "--session", str(_outside_copy(tmp_path, "claude.jsonl")))
    assert result.exit_code == 0, result.output
    assert [link.path for link in _records(repo)[0].links] == ["src/billing/close.py"]


# --- source.ref ---------------------------------------------------------------------------------


def test_source_ref_is_name_only_outside_the_repo(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stage(repo, "a.py")
    session = _outside_copy(tmp_path, "claude.jsonl")
    result = _capture(repo, monkeypatch, "--session", str(session))
    assert result.exit_code == 0, result.output
    record = _records(repo)[0]
    assert record.source.ref == "claude.jsonl"
    saved = next((repo / ".whyline" / "records").glob("*.yml")).read_text(encoding="utf-8")
    assert str(tmp_path) not in saved


def test_source_ref_is_repo_relative_inside_the_repo(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stage(repo, "a.py")
    logs = repo / "logs"
    logs.mkdir()
    shutil.copy(FIXTURES / "plain.txt", logs / "session.txt")
    result = _capture(repo / "logs", monkeypatch, "--session", "session.txt")
    assert result.exit_code == 0, result.output
    assert _records(repo)[0].source.ref == "logs/session.txt"


# --- failures write nothing ---------------------------------------------------------------------


def test_session_with_affirm_exits_1_and_writes_nothing(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stage(repo, "a.py")
    session = _outside_copy(tmp_path, "plain.txt")
    result = _capture(
        repo, monkeypatch, "--session", str(session), "--affirm", "--i-am-human", "--pending"
    )
    assert result.exit_code == 1, result.output
    assert "always a draft" in plain(result.output)
    assert _records(repo) == []
    assert not (repo / ".whyline" / "pending").exists()


def test_session_with_affirm_from_agent_shell_hits_the_human_gate_first(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stage(repo, "a.py")
    session = _outside_copy(tmp_path, "plain.txt")
    result = _capture(repo, monkeypatch, "--session", str(session), "--affirm", "--pending")
    assert result.exit_code == 8, result.output
    assert _records(repo) == []
    assert not (repo / ".whyline" / "pending").exists()


def test_missing_session_file_exits_9(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stage(repo, "a.py")
    result = _capture(repo, monkeypatch, "--session", "nope.jsonl")
    assert result.exit_code == 9, result.output
    assert _records(repo) == []


def test_empty_session_without_goal_exits_1(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stage(repo, "a.py")
    empty = tmp_path / "empty.jsonl"
    empty.write_text("\n\n", encoding="utf-8")
    result = _capture(repo, monkeypatch, "--session", str(empty))
    assert result.exit_code == 1, result.output
    assert "--goal" in plain(result.output)
    assert _records(repo) == []


def test_binary_session_exits_1(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stage(repo, "a.py")
    binary = tmp_path / "s.bin"
    binary.write_bytes(b"\xff\xfe\x00\x81")
    result = _capture(repo, monkeypatch, "--session", str(binary))
    assert result.exit_code == 1, result.output
    assert _records(repo) == []


def test_session_json_output(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stage(repo, "a.py")
    session = _outside_copy(tmp_path, "array.json")
    result = _capture(repo, monkeypatch, "--session", str(session), "--json")
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["record"]["goal"] == "Retry on 429 but not on 500."
    assert data["record"]["source"] == {"kind": "session", "ref": "array.json"}


def test_session_on_a_terminal_asks_no_questions(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("whyline.cli.stdin_is_tty", lambda: True)
    _stage(repo, "a.py")
    session = _outside_copy(tmp_path, "plain.txt")
    result = _capture(repo, monkeypatch, "--session", str(session))
    assert result.exit_code == 0, result.output
    assert "What is this change for?" not in result.output
    assert "What would prove this wrong?" not in result.output
    (record,) = _records(repo)
    assert record.source.kind == "session"
    assert record.rejected == [] and record.falsifier == ""
