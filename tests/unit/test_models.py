"""Tests for the record and config models against docs/03."""

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from gitwhy.models import DEFAULT_CHECK_IGNORE, Config, Record, StoredRecord
from tests.conftest import doc_yaml_block


def _example() -> dict[str, Any]:
    data = yaml.safe_load(doc_yaml_block("## 1. Record schema"))
    assert isinstance(data, dict)
    return data


def _record(**changes: Any) -> dict[str, Any]:
    data = _example()
    data.update(changes)
    return data


def _affirmed(**changes: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "status": "affirmed",
        "affirmed_at": "2026-10-16T09:00:00Z",
        "affirmed_by": "Mahamudul",
    }
    fields.update(changes)
    return _record(**fields)


# --- the documented example ---------------------------------------------------------------


def test_doc_example_validates() -> None:
    record = Record.model_validate(_example())
    assert str(record.id) == "01932a7e-5b1c-7c3a-8f21-9c0e4d2a1b77"
    assert record.status == "draft"
    assert record.created_at == datetime(2026, 10, 15, 13, 4, 11, tzinfo=UTC)
    assert record.links[1].start_line is None


def test_doc_example_round_trips_through_yaml() -> None:
    original = _example()
    dumped = Record.model_validate(original).model_dump(mode="json")
    reloaded = yaml.safe_load(yaml.safe_dump(dumped, sort_keys=False))
    assert reloaded == dumped
    assert Record.model_validate(reloaded) == Record.model_validate(original)
    assert list(dumped) == list(original), "field order must follow docs/03"
    assert dumped["created_at"] == "2026-10-15T13:04:11Z"


def test_affirmed_record_validates() -> None:
    record = Record.model_validate(_affirmed())
    assert record.affirmed_by == "Mahamudul"


def test_timestamps_are_normalized_to_utc() -> None:
    plus_six = timezone(timedelta(hours=6))
    record = Record.model_validate(
        _record(created_at=datetime(2026, 10, 15, 19, 4, 11, tzinfo=plus_six))
    )
    assert record.created_at == datetime(2026, 10, 15, 13, 4, 11, tzinfo=UTC)
    assert record.created_at.tzinfo is UTC


# --- docs/05 required failure modes -------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "../etc/passwd",
        "src/../../etc/passwd",
        "/etc/passwd",
        "C:/Windows",
        "C:\\x",
        "\\\\host\\s",
        "",
    ],
)
def test_link_path_escaping_repo_is_rejected(path: str) -> None:
    data = _record(links=[{"path": path, "start_line": None, "end_line": None}])
    with pytest.raises(ValidationError):
        Record.model_validate(data)


def test_affirmed_record_missing_affirmed_at_is_rejected() -> None:
    with pytest.raises(ValidationError, match="affirmed_at is null while status is affirmed"):
        Record.model_validate(_affirmed(affirmed_at=None))


def test_affirmed_record_missing_affirmed_by_is_rejected() -> None:
    with pytest.raises(ValidationError, match="affirmed_by is empty"):
        Record.model_validate(_affirmed(affirmed_by=None))


def test_draft_with_affirmed_at_is_rejected() -> None:
    with pytest.raises(ValidationError, match="affirmed_at is set while status is draft"):
        Record.model_validate(_record(affirmed_at="2026-10-16T09:00:00Z"))


def test_draft_with_affirmed_by_is_rejected() -> None:
    with pytest.raises(ValidationError, match="affirmed_by is set while status is draft"):
        Record.model_validate(_record(affirmed_by="someone"))


def test_unknown_key_is_rejected_on_write() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Record.model_validate(_record(mood="optimistic"))


def test_unknown_nested_key_is_rejected_on_write() -> None:
    data = _record()
    data["author"]["email"] = "a@example.com"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Record.model_validate(data)


def test_unknown_keys_are_preserved_on_read_round_trip() -> None:
    data = _record(future_field={"nested": [1, 2]})
    data["links"][0]["future_link_field"] = "kept"
    stored = StoredRecord.model_validate(data)
    dumped = stored.model_dump(mode="json")
    assert dumped["future_field"] == {"nested": [1, 2]}
    assert dumped["links"][0]["future_link_field"] == "kept"
    assert StoredRecord.model_validate(yaml.safe_load(yaml.safe_dump(dumped))) == stored


def test_reader_still_validates_known_fields() -> None:
    with pytest.raises(ValidationError):
        StoredRecord.model_validate(_affirmed(affirmed_at=None))


# --- field rules ----------------------------------------------------------------------------


@pytest.mark.parametrize("version", [0, 2, 99, "1"])
def test_unsupported_schema_version_is_rejected(version: object) -> None:
    with pytest.raises(ValidationError):
        Record.model_validate(_record(schema_version=version))


@pytest.mark.parametrize(
    "bad_id",
    [
        "not-a-uuid",
        "0b6f2a2c-5b1c-4c3a-8f21-9c0e4d2a1b77",  # version 4
    ],
)
def test_id_must_be_uuid7(bad_id: str) -> None:
    with pytest.raises(ValidationError):
        Record.model_validate(_record(id=bad_id))


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Record.model_validate(_record(created_at="2026-10-15T13:04:11"))


@pytest.mark.parametrize("status", ["Draft", "confirmed", ""])
def test_unknown_status_is_rejected(status: str) -> None:
    with pytest.raises(ValidationError):
        Record.model_validate(_record(status=status))


def test_agent_author_requires_tool() -> None:
    with pytest.raises(ValidationError, match=r"author\.tool is required"):
        Record.model_validate(_record(author={"kind": "agent", "name": None, "tool": None}))


def test_agent_author_with_tool_is_valid() -> None:
    record = Record.model_validate(_record(author={"kind": "agent", "tool": "claude-code"}))
    assert record.author.name is None


def test_human_author_must_not_name_tool() -> None:
    with pytest.raises(ValidationError, match=r"author\.tool must be null"):
        Record.model_validate(_record(author={"kind": "human", "tool": "claude-code"}))


@pytest.mark.parametrize("goal", ["", "x" * 501])
def test_goal_length_is_bounded(goal: str) -> None:
    with pytest.raises(ValidationError):
        Record.model_validate(_record(goal=goal))


def test_goal_at_limit_is_valid() -> None:
    assert Record.model_validate(_record(goal="x" * 500)).goal == "x" * 500


def test_rejected_option_is_bounded() -> None:
    with pytest.raises(ValidationError):
        Record.model_validate(_record(rejected=[{"option": "x" * 301, "reason": ""}]))
    with pytest.raises(ValidationError):
        Record.model_validate(_record(rejected=[{"option": "", "reason": "why"}]))


def test_rejected_reason_may_be_omitted() -> None:
    record = Record.model_validate(_record(rejected=[{"option": "Do nothing"}]))
    assert record.rejected[0].reason == ""


def test_links_must_not_be_empty() -> None:
    with pytest.raises(ValidationError):
        Record.model_validate(_record(links=[]))


@pytest.mark.parametrize(
    ("start", "end"),
    [(10, 9), (0, 5), (5, 0), (-1, None), (None, 0)],
)
def test_bad_line_ranges_are_rejected(start: int | None, end: int | None) -> None:
    data = _record(links=[{"path": "src/a.py", "start_line": start, "end_line": end}])
    with pytest.raises(ValidationError):
        Record.model_validate(data)


def test_single_line_range_is_valid() -> None:
    data = _record(links=[{"path": "src/a.py", "start_line": 7, "end_line": 7}])
    assert Record.model_validate(data).links[0].end_line == 7


@pytest.mark.parametrize(
    "missing",
    ["constraints", "rejected", "assumptions", "falsifier", "evidence", "links", "risks", "source"],
)
def test_required_list_and_text_fields_must_be_present(missing: str) -> None:
    data = _record()
    del data[missing]
    with pytest.raises(ValidationError):
        Record.model_validate(data)


def test_adr_is_optional() -> None:
    data = _record()
    del data["adr"]
    assert Record.model_validate(data).adr is None


def test_empty_narrative_fields_are_valid_on_a_draft() -> None:
    record = Record.model_validate(
        _record(constraints=[], rejected=[], assumptions=[], falsifier="", evidence=[], risks=[])
    )
    assert record.falsifier == ""


@pytest.mark.parametrize("kind", ["test", "command", "note"])
def test_evidence_kinds(kind: str) -> None:
    record = Record.model_validate(_record(evidence=[{"kind": kind, "ref": "x"}]))
    assert record.evidence[0].exit_code is None


def test_unknown_evidence_and_source_kinds_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Record.model_validate(_record(evidence=[{"kind": "vibes", "ref": "x"}]))
    with pytest.raises(ValidationError):
        Record.model_validate(_record(source={"kind": "llm", "ref": None}))


# --- config -------------------------------------------------------------------------------


def test_doc_config_example_matches_defaults() -> None:
    data = yaml.safe_load(doc_yaml_block("## 2. Config schema"))
    config = Config.model_validate(data)
    assert config == Config()
    assert config.model_dump(mode="json") == data


def test_config_defaults() -> None:
    config = Config()
    assert config.check.enabled is False
    assert config.check.min_lines == 30
    assert tuple(config.check.ignore) == DEFAULT_CHECK_IGNORE
    assert config.hooks.trailer is True
    assert config.hooks.check is False
    assert config.capture.default_author_name is None


def test_partial_config_fills_defaults() -> None:
    config = Config.model_validate({"check": {"min_lines": 50}})
    assert config.check.min_lines == 50
    assert config.check.enabled is False
    assert config.hooks.trailer is True


def test_config_default_ignore_lists_are_independent() -> None:
    first, second = Config(), Config()
    first.check.ignore.append("extra")
    assert "extra" not in second.check.ignore


@pytest.mark.parametrize(
    "data",
    [
        {"chek": {}},
        {"check": {"min_line": 10}},
        {"check": {"min_lines": -1}},
        {"schema_version": 2},
        {"hooks": {"trailer": "sometimes"}},
    ],
)
def test_invalid_config_is_rejected(data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Config.model_validate(data)


def test_boolean_schema_version_is_rejected() -> None:
    with pytest.raises(ValidationError, match="schema_version must be an integer"):
        Record.model_validate(_record(schema_version=True))
    with pytest.raises(ValidationError, match="schema_version must be an integer"):
        Config.model_validate({"schema_version": True})
