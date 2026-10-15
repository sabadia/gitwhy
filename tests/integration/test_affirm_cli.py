"""``intentline affirm`` end to end in a real git repository (docs/05 section 2)."""

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from intentline.cli import app
from intentline.models import Record
from intentline.store import RecordStore, dump_yaml, initialize
from tests.conftest import MakeRecord, plain, record_data, uuid7

runner = CliRunner()
ID = str(uuid7(1))


@pytest.fixture
def repo(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An initialized repo, cwd inside it, with a repo-local git user.name."""
    initialize(git_repo)
    subprocess.run(["git", "-C", str(git_repo), "config", "user.name", "Git User"], check=True)  # noqa: S603, S607
    monkeypatch.chdir(git_repo)
    return git_repo


@pytest.fixture
def store(repo: Path) -> RecordStore:
    return RecordStore(repo / ".intentline")


def _tty(monkeypatch: pytest.MonkeyPatch, value: bool = True) -> None:
    monkeypatch.setattr("intentline.cli.stdin_is_tty", lambda: value)


def _affirm(*args: str, input: str | None = None) -> Result:
    return runner.invoke(app, ["affirm", *args], input=input)


# --- docs/05 required ------------------------------------------------------------------------


def test_non_tty_without_i_am_human_exits_8_and_changes_nothing(
    store: RecordStore, make_record: MakeRecord
) -> None:
    path = store.save(make_record())
    before = path.read_bytes()
    result = _affirm(ID)
    assert result.exit_code == 8
    assert "--i-am-human" in plain(result.output)
    assert path.read_bytes() == before


def test_i_am_human_on_non_tty_succeeds(store: RecordStore) -> None:
    raw = Record.model_validate(record_data(1)).model_dump(mode="json")
    raw["future_field"] = "keep"
    store.path_for(uuid7(1)).write_text(dump_yaml(raw), encoding="utf-8")

    result = _affirm(ID, "--i-am-human")

    assert result.exit_code == 0, result.output
    assert f"Affirmed {ID} by Git User." in result.stdout
    assert "Warning: affirmed with empty fields: constraints" in plain(result.stderr)
    saved = store.load(uuid7(1))
    assert saved.status == "affirmed"
    assert saved.affirmed_by == "Git User"
    assert saved.affirmed_at is not None and saved.affirmed_at.microsecond == 0
    assert saved.updated_at == saved.affirmed_at
    assert saved.model_dump()["future_field"] == "keep"
    assert saved.falsifier == "", "fields must not be filled in"


def test_missing_id_exits_9(repo: Path) -> None:
    assert _affirm(ID, "--i-am-human").exit_code == 9


def test_gate_runs_before_existence_check(repo: Path) -> None:
    assert _affirm(ID).exit_code == 8


def test_malformed_id_exits_1(repo: Path) -> None:
    assert _affirm("../../etc/passwd", "--i-am-human").exit_code == 1


def test_outside_a_repo_exits_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert _affirm(ID, "--i-am-human").exit_code == 2


def test_uninitialized_repo_exits_2(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(git_repo)
    result = _affirm(ID, "--i-am-human", "--by", "Ada")
    assert result.exit_code == 2
    assert "intentline init" in plain(result.output)


# --- who is affirming ------------------------------------------------------------------------


def test_by_flag_overrides_git_user(store: RecordStore, make_record: MakeRecord) -> None:
    store.save(make_record())
    result = _affirm(ID, "--i-am-human", "--by", "Ada Lovelace")
    assert result.exit_code == 0
    assert store.load(uuid7(1)).affirmed_by == "Ada Lovelace"


def test_no_name_anywhere_exits_1(
    store: RecordStore, make_record: MakeRecord, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = store.save(make_record())
    before = path.read_bytes()
    monkeypatch.setattr("intentline.affirm.config_value", lambda key, cwd: None)
    result = _affirm(ID, "--i-am-human")
    assert result.exit_code == 1
    assert "--by" in plain(result.output)
    assert path.read_bytes() == before


# --- interactive terminal --------------------------------------------------------------------


def test_tty_confirm_yes_affirms(
    store: RecordStore, make_record: MakeRecord, monkeypatch: pytest.MonkeyPatch
) -> None:
    _tty(monkeypatch)
    store.save(make_record())
    result = _affirm(ID, input="y\n")
    assert result.exit_code == 0, result.output
    assert "These fields are empty: constraints, rejected" in plain(result.stderr)
    assert store.load(uuid7(1)).status == "affirmed"


def test_tty_confirm_no_exits_1_unchanged(
    store: RecordStore, make_record: MakeRecord, monkeypatch: pytest.MonkeyPatch
) -> None:
    _tty(monkeypatch)
    path = store.save(make_record())
    before = path.read_bytes()
    result = _affirm(ID, input="n\n")
    assert result.exit_code == 1
    assert "Not affirmed" in plain(result.output)
    assert path.read_bytes() == before


def test_tty_yes_flag_skips_prompt(
    store: RecordStore, make_record: MakeRecord, monkeypatch: pytest.MonkeyPatch
) -> None:
    _tty(monkeypatch)
    store.save(make_record())
    result = _affirm(ID, "--yes")
    assert result.exit_code == 0
    assert "Affirm anyway?" not in result.output
    assert store.load(uuid7(1)).status == "affirmed"


def test_tty_full_record_does_not_prompt(
    store: RecordStore, make_record: MakeRecord, monkeypatch: pytest.MonkeyPatch
) -> None:
    _tty(monkeypatch)
    store.save(
        make_record(
            constraints=["c"],
            rejected=[{"option": "o"}],
            assumptions=["a"],
            falsifier="f",
            evidence=[{"kind": "note", "ref": "r"}],
            risks=["r"],
        )
    )
    result = _affirm(ID)
    assert result.exit_code == 0
    assert "Affirm anyway?" not in result.output
    assert result.stderr == ""


def test_yes_does_not_bypass_the_gate(store: RecordStore, make_record: MakeRecord) -> None:
    store.save(make_record())
    assert _affirm(ID, "--yes").exit_code == 8


# --- repeat and JSON ---------------------------------------------------------------------------


def test_already_affirmed_is_a_no_op(store: RecordStore, make_record: MakeRecord) -> None:
    store.save(make_record())
    assert _affirm(ID, "--i-am-human", "--by", "First").exit_code == 0
    before = store.path_for(uuid7(1)).read_bytes()
    result = _affirm(ID, "--i-am-human", "--by", "Second")
    assert result.exit_code == 0
    assert "is already affirmed by First at " in result.stdout
    assert "Z. Nothing changed." in result.stdout
    assert store.path_for(uuid7(1)).read_bytes() == before


def test_json_prints_the_raw_record(store: RecordStore, make_record: MakeRecord) -> None:
    store.save(make_record())
    result = _affirm(ID, "--i-am-human", "--json")
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["id"] == ID
    assert data["status"] == "affirmed"
    assert data["affirmed_by"] == "Git User"
    assert "AFFIRMED" not in result.stdout


def test_help_documents_the_gate() -> None:
    result = runner.invoke(app, ["affirm", "--help"])
    text = plain(result.output)
    assert result.exit_code == 0
    for phrase in ("--i-am-human", "--yes", "--by", "lying", "8 when the human gate refuses"):
        assert phrase in text
