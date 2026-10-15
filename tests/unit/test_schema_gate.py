"""Tests for the schema version gate (docs/02 section 5, docs/03 section 9)."""

import pytest

from intentline.errors import CorruptError, ExitCode, SchemaVersionError
from intentline.store import (
    SCHEMA_VERSION_FILENAME,
    RecordStore,
    dump_yaml,
    ensure_supported_schema,
)
from tests.conftest import MakeRecord, uuid7


def _write_record_with_version(
    store: RecordStore, make_record: MakeRecord, version: object
) -> None:
    data = make_record().model_dump(mode="json")
    data["schema_version"] = version
    (store.records_dir / f"{uuid7(1)}.yml").write_text(dump_yaml(data), encoding="utf-8")


def test_record_with_schema_version_99_exits_6(store: RecordStore, make_record: MakeRecord) -> None:
    _write_record_with_version(store, make_record, 99)
    with pytest.raises(SchemaVersionError) as excinfo:
        store.load(uuid7(1))
    error = excinfo.value
    assert error.exit_code == ExitCode.SCHEMA
    assert int(error.exit_code) == 6
    assert "schema version 99" in str(error)
    assert f".intentline/records/{uuid7(1)}.yml" in str(error)
    assert "Upgrade intentline" in str(error)


def test_newer_record_is_reported_by_list_without_hiding_others(
    store: RecordStore, make_record: MakeRecord
) -> None:
    _write_record_with_version(store, make_record, 2)
    store.save(make_record(2))
    result = store.list()
    assert [r.id for r in result.records] == [uuid7(2)]
    assert len(result.errors) == 1
    assert isinstance(result.errors[0], SchemaVersionError)


@pytest.mark.parametrize("version", [0, "1", "99", None, True, 1.5])
def test_non_integer_or_old_versions_are_corrupt_not_schema(
    store: RecordStore, make_record: MakeRecord, version: object
) -> None:
    _write_record_with_version(store, make_record, version)
    with pytest.raises(CorruptError):
        store.load(uuid7(1))


def test_current_version_loads(store: RecordStore, make_record: MakeRecord) -> None:
    store.save(make_record())
    assert store.load(uuid7(1)).schema_version == 1


def test_missing_schema_version_key_is_corrupt(store: RecordStore, make_record: MakeRecord) -> None:
    data = make_record().model_dump(mode="json")
    del data["schema_version"]
    (store.records_dir / f"{uuid7(1)}.yml").write_text(dump_yaml(data), encoding="utf-8")
    with pytest.raises(CorruptError, match="schema_version"):
        store.load(uuid7(1))


# --- repository-level .intentline/schema-version ----------------------------------------------


def test_newer_repository_schema_blocks_every_operation(
    store: RecordStore, make_record: MakeRecord
) -> None:
    store.save(make_record())
    (store.intentline_dir / SCHEMA_VERSION_FILENAME).write_text("2\n", encoding="utf-8")
    for operation in (lambda: store.load(uuid7(1)), store.list, lambda: store.save(make_record())):
        with pytest.raises(SchemaVersionError, match=r"\.intentline/schema-version") as excinfo:
            operation()
        assert excinfo.value.exit_code == ExitCode.SCHEMA


def test_saving_into_newer_repository_writes_nothing(
    store: RecordStore, make_record: MakeRecord
) -> None:
    (store.intentline_dir / SCHEMA_VERSION_FILENAME).write_text("3", encoding="utf-8")
    with pytest.raises(SchemaVersionError):
        store.save(make_record())
    assert list(store.records_dir.iterdir()) == []


@pytest.mark.parametrize("text", ["1\n", "1", " 1 \n"])
def test_current_repository_schema_is_accepted(
    store: RecordStore, make_record: MakeRecord, text: str
) -> None:
    (store.intentline_dir / SCHEMA_VERSION_FILENAME).write_text(text, encoding="utf-8")
    store.save(make_record())
    assert len(store.list().records) == 1


def test_missing_repository_schema_file_is_accepted(
    store: RecordStore, make_record: MakeRecord
) -> None:
    store.save(make_record())
    assert store.load(uuid7(1)).id == uuid7(1)


@pytest.mark.parametrize("text", ["one", "", "1.0"])
def test_garbled_repository_schema_file_is_corrupt(store: RecordStore, text: str) -> None:
    (store.intentline_dir / SCHEMA_VERSION_FILENAME).write_text(text, encoding="utf-8")
    with pytest.raises(CorruptError, match="schema version number"):
        store.list()


def test_unreadable_repository_schema_file_is_corrupt(store: RecordStore) -> None:
    (store.intentline_dir / SCHEMA_VERSION_FILENAME).write_bytes(b"\xff\xfe")
    with pytest.raises(CorruptError, match="Cannot read"):
        store.list()


# --- the gate function itself -----------------------------------------------------------------


@pytest.mark.parametrize("version", [1, 0, -5, None, "2", True, 2.0])
def test_gate_only_rejects_newer_integers(version: object) -> None:
    ensure_supported_schema(version, "thing")


def test_gate_rejects_newer_integer() -> None:
    with pytest.raises(SchemaVersionError, match="thing uses schema version 2"):
        ensure_supported_schema(2, "thing")
