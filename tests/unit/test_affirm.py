"""The affirm rules: human gate, empty-field confirmation, and the affirmed copy."""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from gitwhy.affirm import (
    EMPTY_FIELD_NAMES,
    AffirmOutcome,
    affirm_record,
    apply_affirmation,
    empty_narrative_fields,
    require_human,
    resolve_affirmer,
)
from gitwhy.errors import AffirmRefusedError, ExitCode, NotFoundError, UsageError
from gitwhy.models import Record, StoredRecord
from gitwhy.store import RecordStore, dump_yaml
from tests.conftest import MakeRecord, record_data, uuid7

NOW = datetime(2026, 10, 16, 9, 0, 0, tzinfo=UTC)

FULL = {
    "constraints": ["Keep the API shape"],
    "rejected": [{"option": "Per-request close", "reason": "Breaks discounts"}],
    "assumptions": ["Invoices are mutable until close"],
    "falsifier": "A customer is charged early",
    "evidence": [{"kind": "test", "ref": "tests/test_close.py::test_daily"}],
    "risks": ["No lock on the close job"],
}


def _never_confirm(fields: list[str]) -> bool:
    raise AssertionError(f"confirm must not be called (fields: {fields})")


def _affirm(
    store: RecordStore,
    *,
    by: str = "Ada",
    interactive: bool = True,
    i_am_human: bool = False,
    yes: bool = False,
    confirm: Callable[[list[str]], bool] = _never_confirm,
    now: datetime = NOW,
) -> AffirmOutcome:
    return affirm_record(
        store,
        uuid7(1),
        by=by,
        interactive=interactive,
        i_am_human=i_am_human,
        yes=yes,
        confirm=confirm,
        now=now,
    )


# --- require_human -----------------------------------------------------------------------------


def test_gate_refuses_non_interactive_without_override() -> None:
    with pytest.raises(AffirmRefusedError, match="human decision") as excinfo:
        require_human(interactive=False, i_am_human=False)
    assert excinfo.value.exit_code == ExitCode.AFFIRM_REFUSED
    assert "--i-am-human" in str(excinfo.value)
    assert "lying" in str(excinfo.value)


@pytest.mark.parametrize(
    ("interactive", "i_am_human"), [(True, False), (False, True), (True, True)]
)
def test_gate_allows_terminal_or_explicit_human(interactive: bool, i_am_human: bool) -> None:
    require_human(interactive=interactive, i_am_human=i_am_human)


# --- empty_narrative_fields / apply_affirmation ------------------------------------------------


def test_empty_fields_in_declared_order(make_record: MakeRecord) -> None:
    assert empty_narrative_fields(make_record()) == list(EMPTY_FIELD_NAMES)
    assert empty_narrative_fields(make_record(**FULL)) == []
    partial = make_record(falsifier="x", risks=["y"])
    assert empty_narrative_fields(partial) == ["constraints", "rejected", "assumptions", "evidence"]


def test_apply_affirmation_sets_only_affirmation_fields(make_record: MakeRecord) -> None:
    draft = make_record()
    affirmed = apply_affirmation(draft, by="Ada", now=NOW)
    assert isinstance(affirmed, Record)
    assert affirmed.status == "affirmed"
    assert affirmed.affirmed_at == NOW
    assert affirmed.updated_at == NOW
    assert affirmed.affirmed_by == "Ada"
    unchanged = {"status", "affirmed_at", "affirmed_by", "updated_at"}
    assert affirmed.model_dump(exclude=unchanged) == draft.model_dump(exclude=unchanged)
    assert draft.status == "draft", "the input must not be mutated"


def test_apply_affirmation_keeps_unknown_keys() -> None:
    stored = StoredRecord.model_validate(record_data(1, future_field="keep"))
    affirmed = apply_affirmation(stored, by="Ada", now=NOW)
    assert isinstance(affirmed, StoredRecord)
    assert affirmed.model_dump()["future_field"] == "keep"


# --- resolve_affirmer --------------------------------------------------------------------------


def test_affirmer_prefers_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("gitwhy.affirm.config_value", lambda key, cwd: "Git Name")
    assert resolve_affirmer("  Flag Name ", tmp_path) == "Flag Name"


@pytest.mark.parametrize("flag", [None, "", "   "])
def test_affirmer_falls_back_to_git_user_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flag: str | None
) -> None:
    monkeypatch.setattr("gitwhy.affirm.config_value", lambda key, cwd: "Git Name")
    assert resolve_affirmer(flag, tmp_path) == "Git Name"


@pytest.mark.parametrize("git_name", [None, "  "])
def test_affirmer_missing_is_usage_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, git_name: str | None
) -> None:
    monkeypatch.setattr("gitwhy.affirm.config_value", lambda key, cwd: git_name)
    with pytest.raises(UsageError, match="--by") as excinfo:
        resolve_affirmer(None, tmp_path)
    assert excinfo.value.exit_code == ExitCode.USAGE


# --- affirm_record -----------------------------------------------------------------------------


def test_gate_runs_before_the_record_is_loaded(store: RecordStore) -> None:
    with pytest.raises(AffirmRefusedError):
        _affirm(store, interactive=False)  # uuid7(1) does not exist: the gate must win


def test_missing_record_is_not_found(store: RecordStore) -> None:
    with pytest.raises(NotFoundError):
        _affirm(store)


def test_non_interactive_refusal_writes_nothing(
    store: RecordStore, make_record: MakeRecord
) -> None:
    path = store.save(make_record())
    before = path.read_bytes()
    with pytest.raises(AffirmRefusedError):
        _affirm(store, interactive=False)
    assert path.read_bytes() == before


def test_full_record_affirms_without_asking(store: RecordStore, make_record: MakeRecord) -> None:
    store.save(make_record(**FULL))
    outcome = _affirm(store)
    saved = store.load(uuid7(1))
    assert saved.status == "affirmed"
    assert saved.affirmed_by == "Ada"
    assert saved.affirmed_at == NOW
    assert outcome.empty_fields == []


def test_empty_fields_are_confirmed_on_a_terminal(
    store: RecordStore, make_record: MakeRecord
) -> None:
    store.save(make_record())
    asked: list[list[str]] = []

    def confirm(fields: list[str]) -> bool:
        asked.append(fields)
        return True

    _affirm(store, confirm=confirm)
    assert asked == [list(EMPTY_FIELD_NAMES)]
    saved = store.load(uuid7(1))
    assert saved.status == "affirmed"
    assert saved.falsifier == "" and saved.rejected == [], "fields must never be filled in"


def test_declined_confirmation_is_usage_error_and_unchanged(
    store: RecordStore, make_record: MakeRecord
) -> None:
    path = store.save(make_record())
    before = path.read_bytes()
    with pytest.raises(UsageError, match="Not affirmed"):
        _affirm(store, confirm=lambda fields: False)
    assert path.read_bytes() == before


def test_yes_skips_confirmation(store: RecordStore, make_record: MakeRecord) -> None:
    store.save(make_record())
    outcome = _affirm(store, yes=True)
    assert outcome.empty_fields == list(EMPTY_FIELD_NAMES)
    assert store.load(uuid7(1)).status == "affirmed"


def test_i_am_human_does_not_prompt_and_reports_empty_fields(
    store: RecordStore, make_record: MakeRecord
) -> None:
    store.save(make_record())
    outcome = _affirm(store, interactive=False, i_am_human=True)
    assert outcome.empty_fields == list(EMPTY_FIELD_NAMES)
    assert store.load(uuid7(1)).status == "affirmed"


def test_already_affirmed_is_unchanged(store: RecordStore, make_record: MakeRecord) -> None:
    store.save(make_record(**FULL))
    _affirm(store, by="First")
    path = store.path_for(uuid7(1))
    before = path.read_bytes()
    outcome = _affirm(store, by="Second", now=datetime(2027, 1, 1, tzinfo=UTC))
    assert outcome.already_affirmed is True
    assert outcome.record.affirmed_by == "First"
    assert path.read_bytes() == before


def test_unknown_keys_survive_affirm(store: RecordStore) -> None:
    raw = Record.model_validate(record_data(1)).model_dump(mode="json")
    raw["future_field"] = "keep"
    store.path_for(uuid7(1)).write_text(dump_yaml(raw), encoding="utf-8")
    _affirm(store, yes=True)
    assert store.load(uuid7(1)).model_dump()["future_field"] == "keep"
