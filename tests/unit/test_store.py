"""Tests for the atomic record store."""

import os
from pathlib import Path

import pytest
import yaml

from tests.conftest import MakeRecord, record_data, uuid7
from whyline.errors import CorruptError, ExitCode, NoRepoError, NotFoundError, UsageError
from whyline.models import Link, Record
from whyline.store import RecordStore, dump_yaml


def _write(store: RecordStore, name: str, text: str) -> Path:
    path = store.records_dir / name
    path.write_text(text, encoding="utf-8")
    return path


def _leftover_temp_files(store: RecordStore) -> list[Path]:
    return [p for p in store.records_dir.iterdir() if p.name.endswith(".tmp")]


# --- save / load --------------------------------------------------------------------------


def test_save_then_load_round_trips(store: RecordStore, make_record: MakeRecord) -> None:
    record = make_record()
    path = store.save(record)
    assert path == store.records_dir / f"{record.id}.yml"
    loaded = store.load(record.id)
    assert Record.model_validate(loaded.model_dump()) == record
    assert _leftover_temp_files(store) == []


def test_saved_file_is_block_yaml_in_schema_order(
    store: RecordStore, make_record: MakeRecord
) -> None:
    text = store.save(make_record()).read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert text.startswith("schema_version: 1\nid: ")
    assert "{" not in text and "&" not in text and "*" not in text
    assert "created_at: '2026-10-15T13:00:01Z'" in text


def test_load_accepts_string_id(store: RecordStore, make_record: MakeRecord) -> None:
    record = make_record()
    store.save(record)
    assert store.load(str(record.id)).id == record.id


def test_save_overwrites_existing_record(store: RecordStore, make_record: MakeRecord) -> None:
    store.save(make_record(goal="first"))
    store.save(make_record(goal="second"))
    assert store.load(uuid7(1)).goal == "second"
    assert len(list(store.records_dir.glob("*.yml"))) == 1


@pytest.mark.parametrize("goal", ["yes", "no", "null", "~", "2026-10-15", "1.0", "on", "# hi"])
def test_yaml_lookalike_strings_survive(
    store: RecordStore, make_record: MakeRecord, goal: str
) -> None:
    store.save(make_record(goal=goal))
    assert store.load(uuid7(1)).goal == goal


def test_unicode_and_long_goal_survive(store: RecordStore, make_record: MakeRecord) -> None:
    goal = "সমাপ্তি — close invoices daily " + "x" * 460
    text = store.save(make_record(goal=goal)).read_text(encoding="utf-8")
    assert store.load(uuid7(1)).goal == goal
    assert f"goal: {goal}\n" in text, "goal must stay on one line and unescaped"


def test_unknown_keys_survive_load_and_save(store: RecordStore) -> None:
    raw = Record.model_validate(record_data(1)).model_dump(mode="json")
    raw["future_field"] = "keep me"
    raw["author"]["pronoun_hint"] = "they"
    path = _write(store, f"{uuid7(1)}.yml", dump_yaml(raw))

    store.save(store.load(uuid7(1)))

    reloaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert reloaded["future_field"] == "keep me"
    assert reloaded["author"]["pronoun_hint"] == "they"


def test_save_rejects_link_escaping_repo(store: RecordStore, make_record: MakeRecord) -> None:
    record = make_record()
    bad = record.model_copy(
        update={
            "links": [Link.model_construct(path="../etc/passwd", start_line=None, end_line=None)]
        }
    )
    with pytest.raises(CorruptError, match=r"\.\.") as excinfo:
        store.save(bad)
    assert excinfo.value.exit_code == ExitCode.CORRUPT
    assert list(store.records_dir.iterdir()) == []


def test_save_requires_init(tmp_path: Path, make_record: MakeRecord) -> None:
    store = RecordStore(tmp_path / ".whyline")
    with pytest.raises(NoRepoError, match="whyline init") as excinfo:
        store.save(make_record())
    assert excinfo.value.exit_code == ExitCode.NO_REPO
    assert not (tmp_path / ".whyline").exists()


def test_failed_write_keeps_original_and_cleans_up(
    store: RecordStore, make_record: MakeRecord, monkeypatch: pytest.MonkeyPatch
) -> None:
    store.save(make_record(goal="original"))

    def boom(fd: int) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "fsync", boom)
    with pytest.raises(OSError, match="disk full"):
        store.save(make_record(goal="replacement"))
    monkeypatch.undo()

    assert store.load(uuid7(1)).goal == "original"
    assert _leftover_temp_files(store) == []


# --- load failures --------------------------------------------------------------------------


def test_load_missing_id_is_not_found(store: RecordStore) -> None:
    with pytest.raises(NotFoundError, match=str(uuid7(5))) as excinfo:
        store.load(uuid7(5))
    assert excinfo.value.exit_code == ExitCode.NOT_FOUND


@pytest.mark.parametrize("bad_id", ["abc", "../../etc/passwd", "", "01932a7e"])
def test_load_rejects_malformed_id(store: RecordStore, bad_id: str) -> None:
    with pytest.raises(UsageError, match="is not a record id"):
        store.load(bad_id)


def test_load_requires_init(tmp_path: Path) -> None:
    with pytest.raises(NoRepoError):
        RecordStore(tmp_path / ".whyline").load(uuid7(1))


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("schema_version: 1\nid: [unclosed\n", "not valid YAML"),
        ("- just\n- a list\n", "not a YAML mapping"),
        ("", "not a YAML mapping"),
        ("schema_version: 1\n", "failed validation"),
    ],
)
def test_load_corrupt_file_fails_cleanly(store: RecordStore, text: str, match: str) -> None:
    _write(store, f"{uuid7(1)}.yml", text)
    with pytest.raises(CorruptError, match=match) as excinfo:
        store.load(uuid7(1))
    assert excinfo.value.exit_code == ExitCode.CORRUPT
    assert f".whyline/records/{uuid7(1)}.yml" in str(excinfo.value)
    assert "whyline capture" in str(excinfo.value)


def test_load_rejects_link_escaping_repo_on_disk(store: RecordStore) -> None:
    data = Record.model_validate(record_data(1)).model_dump(mode="json")
    data["links"] = [{"path": "/etc/passwd", "start_line": None, "end_line": None}]
    _write(store, f"{uuid7(1)}.yml", dump_yaml(data))
    with pytest.raises(CorruptError, match=r"links\.0\.path"):
        store.load(uuid7(1))


def test_load_rejects_non_utf8(store: RecordStore) -> None:
    (store.records_dir / f"{uuid7(1)}.yml").write_bytes(b"goal: \xff\xfe\n")
    with pytest.raises(CorruptError, match="not UTF-8"):
        store.load(uuid7(1))


def test_load_rejects_id_that_does_not_match_file_name(
    store: RecordStore, make_record: MakeRecord
) -> None:
    path = store.save(make_record(1))
    path.rename(store.records_dir / f"{uuid7(2)}.yml")
    with pytest.raises(CorruptError, match="does not match its file name"):
        store.load(uuid7(2))


def test_load_path_missing_file(store: RecordStore) -> None:
    with pytest.raises(NotFoundError):
        store.load_path(store.records_dir / "nope.yml")


def test_many_validation_errors_are_summarized(store: RecordStore) -> None:
    _write(store, f"{uuid7(1)}.yml", "schema_version: 1\nid: x\nstatus: maybe\n")
    with pytest.raises(CorruptError, match=r"and \d+ more"):
        store.load(uuid7(1))


# --- list -----------------------------------------------------------------------------------


def test_list_returns_all_records(store: RecordStore, make_record: MakeRecord) -> None:
    for n in (3, 1, 2):
        store.save(make_record(n))
    result = store.list()
    assert [r.id for r in result.records] == [uuid7(1), uuid7(2), uuid7(3)]
    assert result.errors == []


def test_list_skips_corrupt_files_and_reports_them(
    store: RecordStore, make_record: MakeRecord
) -> None:
    store.save(make_record(1))
    store.save(make_record(3))
    _write(store, f"{uuid7(2)}.yml", "not: [valid\n")
    result = store.list()
    assert [r.id for r in result.records] == [uuid7(1), uuid7(3)]
    assert len(result.errors) == 1
    assert isinstance(result.errors[0], CorruptError)
    assert str(uuid7(2)) in str(result.errors[0])


def test_list_ignores_non_record_files(store: RecordStore, make_record: MakeRecord) -> None:
    store.save(make_record(1))
    (store.records_dir / ".gitkeep").touch()
    (store.records_dir / "notes.txt").write_text("hi", encoding="utf-8")
    (store.records_dir / f".{uuid7(9)}.yml").write_text("partial", encoding="utf-8")
    result = store.list()
    assert [r.id for r in result.records] == [uuid7(1)]
    assert result.errors == []


def test_list_empty_store(store: RecordStore) -> None:
    result = store.list()
    assert result.records == [] and result.errors == []


def test_list_requires_init(tmp_path: Path) -> None:
    with pytest.raises(NoRepoError):
        RecordStore(tmp_path / ".whyline").list()


def test_display_falls_back_to_absolute_path(tmp_path: Path) -> None:
    store = RecordStore(tmp_path / ".whyline")
    outside = Path("/somewhere/else.yml")
    assert store._display(outside) == str(outside)


def test_mentioning_skips_other_paths_and_reports_a_bad_file(
    store: RecordStore, make_record: MakeRecord
) -> None:
    store.save(make_record(1, links=[{"path": "src/app.py", "start_line": 1, "end_line": 1}]))
    other = {"path": "other/file.py", "start_line": None, "end_line": None}
    store.save(make_record(2, links=[other]))
    (store.records_dir / f"{uuid7(3)}.yml").write_bytes(b"\xff path: src/app.py\n")
    broken = "path: src/app.py\n[broken\n"
    (store.records_dir / f"{uuid7(4)}.yml").write_text(broken, encoding="utf-8")

    result = store.mentioning("src/app.py")

    assert [record.id for record in result.records] == [uuid7(1)]
    assert len(result.errors) == 2
    messages = " ".join(error.message for error in result.errors)
    assert "UTF-8" in messages
    assert "not valid YAML" in messages
