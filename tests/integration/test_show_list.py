"""``gitwhy show`` and ``gitwhy list`` against real git repositories."""

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner, Result

from gitwhy.cli import app
from gitwhy.models import Record
from gitwhy.render import BANNER_AFFIRMED, BANNER_DRAFT
from gitwhy.store import RecordStore, dump_yaml, initialize
from tests.conftest import plain, record_data, uuid7

runner = CliRunner()

AFFIRMED: dict[str, Any] = {
    "status": "affirmed",
    "affirmed_at": "2026-10-16T09:00:00Z",
    "affirmed_by": "Ada",
}


@pytest.fixture
def repo(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    initialize(git_repo)
    monkeypatch.chdir(git_repo)
    return git_repo


def _save(repo: Path, n: int, **overrides: Any) -> None:
    RecordStore(repo / ".gitwhy").save(Record.model_validate(record_data(n, **overrides)))


def _run(*args: str) -> Result:
    return runner.invoke(app, list(args))


# --- show -----------------------------------------------------------------------------------


def test_show_draft_has_draft_banner(repo: Path) -> None:
    _save(repo, 1)
    result = _run("show", str(uuid7(1)))
    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines()[0] == BANNER_DRAFT
    assert "goal: Goal number 1" in result.stdout
    assert "falsifier: (none)" in result.stdout


def test_show_affirmed_has_affirmed_banner(repo: Path) -> None:
    _save(repo, 1, **AFFIRMED)
    result = _run("show", str(uuid7(1)))
    assert result.exit_code == 0
    assert result.stdout.splitlines()[0] == BANNER_AFFIRMED
    assert "affirmed: 2026-10-16T09:00:00Z by Ada" in result.stdout


def test_show_json_is_raw_record_without_banner(repo: Path) -> None:
    gitwhy = repo / ".gitwhy"
    data = Record.model_validate(record_data(1)).model_dump(mode="json")
    data["future_field"] = "kept"
    (gitwhy / "records" / f"{uuid7(1)}.yml").write_text(dump_yaml(data), encoding="utf-8")
    result = _run("show", str(uuid7(1)), "--json")
    assert result.exit_code == 0
    assert json.loads(result.stdout) == data
    assert "DRAFT" not in result.stdout


def test_show_missing_id_exits_9(repo: Path) -> None:
    result = _run("show", str(uuid7(42)))
    assert result.exit_code == 9
    assert "No record with id" in plain(result.output)


def test_show_malformed_id_exits_1(repo: Path) -> None:
    assert _run("show", "../../etc/passwd").exit_code == 1


def test_show_corrupt_yaml_exits_4(repo: Path) -> None:
    (repo / ".gitwhy" / "records" / f"{uuid7(1)}.yml").write_text("goal: [x\n")
    result = _run("show", str(uuid7(1)))
    assert result.exit_code == 4
    assert "is not valid YAML" in plain(result.output)


# --- list -----------------------------------------------------------------------------------


def test_list_empty(repo: Path) -> None:
    result = _run("list")
    assert result.exit_code == 0
    assert result.stdout.strip() == "No records."


def test_list_newest_first_with_banners(repo: Path) -> None:
    _save(repo, 1)
    _save(repo, 2, **AFFIRMED)
    _save(repo, 3)
    result = _run("list")
    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    assert [line.split()[1] for line in lines] == [str(uuid7(n)) for n in (3, 2, 1)]
    assert [line.split()[0] for line in lines] == ["DRAFT", "AFFIRMED", "DRAFT"]


def test_list_corrupt_file_warns_and_lists_others(repo: Path) -> None:
    _save(repo, 1)
    _save(repo, 3)
    (repo / ".gitwhy" / "records" / f"{uuid7(2)}.yml").write_text("not: [valid\n")
    result = _run("list")
    assert result.exit_code == 0
    assert result.stderr.startswith("warning: ")
    assert str(uuid7(2)) in plain(result.stderr)
    ids = [line.split()[1] for line in result.stdout.splitlines()]
    assert ids == [str(uuid7(3)), str(uuid7(1))]


def test_list_newer_schema_file_is_skipped_with_warning(repo: Path) -> None:
    data = Record.model_validate(record_data(1)).model_dump(mode="json")
    data["schema_version"] = 2
    (repo / ".gitwhy" / "records" / f"{uuid7(1)}.yml").write_text(dump_yaml(data))
    result = _run("list", "--json")
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["records"] == []
    assert payload["skipped"][0]["exit_code"] == 6
    assert "schema version 2" in payload["skipped"][0]["message"]
    assert "warning:" in result.stderr


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["--status", "affirmed"], [2]),
        (["--status", "draft"], [3, 1]),
        (["--author", "agent"], [3]),
        (["--author", "human"], [2, 1]),
        (["--path", "src/billing"], [2, 1]),
        (["--path", "./docs/"], [3]),
        (["--status", "draft", "--path", "src/"], [1]),
    ],
)
def test_list_filters(repo: Path, args: list[str], expected: list[int]) -> None:
    _save(repo, 1, links=[{"path": "src/billing/close.py"}])
    _save(repo, 2, links=[{"path": "src/billing/models.py"}], **AFFIRMED)
    _save(repo, 3, links=[{"path": "docs/a.md"}], author={"kind": "agent", "tool": "codex"})
    result = _run("list", "--json", *args)
    assert result.exit_code == 0
    assert [r["id"] for r in json.loads(result.stdout)["records"]] == [
        str(uuid7(n)) for n in expected
    ]


def test_list_json_shape_is_stable(repo: Path) -> None:
    _save(repo, 1)
    payload = json.loads(_run("list", "--json").stdout)
    assert set(payload) == {"records", "skipped"}
    assert payload["skipped"] == []
    assert payload["records"][0] == Record.model_validate(record_data(1)).model_dump(mode="json")


@pytest.mark.parametrize("args", [["--status", "maybe"], ["--author", "robot"]])
def test_list_bad_filter_value_exits_1(repo: Path, args: list[str]) -> None:
    assert _run("list", *args).exit_code == 1


# --- environment failures -------------------------------------------------------------------


@pytest.mark.parametrize("args", [["list"], ["show", str(uuid7(1))]])
def test_outside_a_repo_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, args: list[str]
) -> None:
    plain_dir = tmp_path / "plain"
    plain_dir.mkdir()
    monkeypatch.chdir(plain_dir)
    assert _run(*args).exit_code == 2


@pytest.mark.parametrize("args", [["list"], ["show", str(uuid7(1))]])
def test_not_initialized_exits_2(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, args: list[str]
) -> None:
    monkeypatch.chdir(git_repo)
    result = _run(*args)
    assert result.exit_code == 2
    assert "gitwhy init" in plain(result.output)
