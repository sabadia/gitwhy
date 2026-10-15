"""Pure capture logic: building drafts and resolving files (docs/03 section 4)."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.conftest import uuid7
from whyline.capture import (
    CaptureInput,
    build_record,
    new_record_id,
    pair_rejected,
    resolve_files,
)
from whyline.errors import ExitCode, UsageError

NOW = datetime(2026, 10, 15, 13, 4, 11, tzinfo=UTC)
ROOT = Path("/repo")


def test_minimal_input_builds_an_empty_honest_draft() -> None:
    record = build_record(
        CaptureInput(goal="Close invoices daily"), record_id=uuid7(1), now=NOW, files=["a.py"]
    )
    assert record.status == "draft"
    assert record.affirmed_at is None and record.affirmed_by is None
    assert record.goal == "Close invoices daily"
    assert record.constraints == [] and record.rejected == [] and record.assumptions == []
    assert record.falsifier == "" and record.evidence == [] and record.risks == []
    assert record.adr is None
    assert (
        record.author.kind == "human" and record.author.tool is None and record.author.name is None
    )
    assert record.source.kind == "flags" and record.source.ref is None
    assert record.created_at == record.updated_at == NOW
    assert [link.path for link in record.links] == ["a.py"]
    assert record.links[0].start_line is None and record.links[0].end_line is None


def test_every_field_is_copied_exactly() -> None:
    inp = CaptureInput(
        goal="  Keep spaces  ",
        constraints=("No API change", "No new deps"),
        rejected=("Per-request close", "Cron"),
        rejected_reasons=("Breaks batch discount",),
        assumptions=("Invoices mutable until close",),
        falsifier="Customer charged before close",
        risks=("No lock",),
        evidence_test="tests/test_close.py::test_daily_close",
        adr="docs/decisions/0042.md",
        author_name="Ada",
        source_kind="session",
        source_ref="session.jsonl",
    )
    record = build_record(inp, record_id=uuid7(2), now=NOW, files=["src/a.py", "src/b.py"])
    assert record.goal == "  Keep spaces  "
    assert record.constraints == ["No API change", "No new deps"]
    assert [(r.option, r.reason) for r in record.rejected] == [
        ("Per-request close", "Breaks batch discount"),
        ("Cron", ""),
    ]
    assert record.assumptions == ["Invoices mutable until close"]
    assert record.falsifier == "Customer charged before close"
    assert record.risks == ["No lock"]
    assert [(e.kind, e.ref, e.exit_code) for e in record.evidence] == [
        ("test", "tests/test_close.py::test_daily_close", None)
    ]
    assert record.adr == "docs/decisions/0042.md"
    assert record.author.name == "Ada"
    assert (record.source.kind, record.source.ref) == ("session", "session.jsonl")
    assert [link.path for link in record.links] == ["src/a.py", "src/b.py"]


def test_agent_tool_makes_an_agent_author() -> None:
    record = build_record(
        CaptureInput(goal="g", agent_tool="claude-code"), record_id=uuid7(1), now=NOW, files=["a"]
    )
    assert (record.author.kind, record.author.tool) == ("agent", "claude-code")


def test_empty_agent_tool_means_human() -> None:
    record = build_record(
        CaptureInput(goal="g", agent_tool=""), record_id=uuid7(1), now=NOW, files=["a"]
    )
    assert (record.author.kind, record.author.tool) == ("human", None)


@pytest.mark.parametrize(
    "inp",
    [
        CaptureInput(goal=""),
        CaptureInput(goal="x" * 501),
        CaptureInput(goal="g", rejected=("x" * 301,)),
    ],
)
def test_schema_violations_are_usage_errors(inp: CaptureInput) -> None:
    with pytest.raises(UsageError, match="Cannot capture this record") as excinfo:
        build_record(inp, record_id=uuid7(1), now=NOW, files=["a"])
    assert excinfo.value.exit_code == ExitCode.USAGE


def test_unsafe_link_path_is_a_usage_error() -> None:
    with pytest.raises(UsageError, match="links"):
        build_record(CaptureInput(goal="g"), record_id=uuid7(1), now=NOW, files=["../etc/passwd"])


def test_no_files_is_a_usage_error() -> None:
    with pytest.raises(UsageError, match="links"):
        build_record(CaptureInput(goal="g"), record_id=uuid7(1), now=NOW, files=[])


# --- rejected pairing ------------------------------------------------------------------------


def test_pair_rejected_by_index() -> None:
    assert pair_rejected(["a", "b"], ["ra", "rb"]) == [
        {"option": "a", "reason": "ra"},
        {"option": "b", "reason": "rb"},
    ]
    assert pair_rejected(["a", "b"], []) == [
        {"option": "a", "reason": ""},
        {"option": "b", "reason": ""},
    ]
    assert pair_rejected([], []) == []


def test_more_reasons_than_options_is_a_usage_error() -> None:
    with pytest.raises(UsageError, match="2 --rejected-reason values but only 1"):
        pair_rejected(["a"], ["r1", "r2"])


# --- file resolution -------------------------------------------------------------------------


def test_resolve_relative_to_cwd_in_subdirectory() -> None:
    assert resolve_files(["app.py", "../README.md"], cwd=ROOT / "src", root=ROOT) == [
        "src/app.py",
        "README.md",
    ]


def test_resolve_absolute_path_inside_repo() -> None:
    assert resolve_files(["/repo/src/x.py"], cwd=ROOT, root=ROOT) == ["src/x.py"]


def test_resolve_deduplicates_and_keeps_order() -> None:
    assert resolve_files(["b.py", "a.py", "./b.py", "src/../b.py"], cwd=ROOT, root=ROOT) == [
        "b.py",
        "a.py",
    ]


def test_resolve_does_not_require_files_to_exist() -> None:
    assert resolve_files(["deleted/file.py"], cwd=ROOT, root=ROOT) == ["deleted/file.py"]


@pytest.mark.parametrize("raw", ["../outside.py", "/etc/passwd", "src/../../x"])
def test_resolve_rejects_paths_outside_repo(raw: str) -> None:
    with pytest.raises(UsageError, match="outside the repository"):
        resolve_files([raw], cwd=ROOT, root=ROOT)


def test_resolve_rejects_repo_root_itself() -> None:
    with pytest.raises(UsageError, match="repository root"):
        resolve_files(["."], cwd=ROOT, root=ROOT)


def test_lexical_normalization_cannot_climb_above_filesystem_root() -> None:
    assert resolve_files(["/../../repo/a.py"], cwd=ROOT, root=ROOT) == ["a.py"]


# --- ids -------------------------------------------------------------------------------------


def test_new_record_ids_are_unique_plain_uuid7() -> None:
    first, second = new_record_id(), new_record_id()
    assert first != second
    assert first.version == 7 and second.version == 7
    assert type(first).__module__ == "uuid"
