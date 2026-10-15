"""Rendering, filtering, and ordering of records."""

from datetime import UTC, datetime
from typing import Any

from gitwhy.models import Record
from gitwhy.render import (
    BANNER_AFFIRMED,
    BANNER_DRAFT,
    LIST_WIDTH,
    NONE_MARKER,
    banner,
    filter_records,
    render_list_line,
    render_record,
)
from tests.conftest import record_data, uuid7

AFFIRMED: dict[str, Any] = {
    "status": "affirmed",
    "affirmed_at": "2026-10-16T09:00:00Z",
    "affirmed_by": "Ada",
}


def _record(n: int = 1, **overrides: Any) -> Record:
    return Record.model_validate(record_data(n, **overrides))


def test_banners() -> None:
    assert banner(_record()) == BANNER_DRAFT == "DRAFT — not a confirmed reason"
    assert banner(_record(**AFFIRMED)) == BANNER_AFFIRMED == "AFFIRMED"


def test_draft_render_starts_with_draft_banner_and_shows_gaps() -> None:
    text = render_record(_record())
    lines = text.splitlines()
    assert lines[0] == BANNER_DRAFT
    assert lines[1] == f"id: {uuid7(1)}"
    assert lines[2] == "goal: Goal number 1"
    for field in ("falsifier", "rejected", "assumptions", "evidence", "constraints", "risks"):
        assert f"{field}: {NONE_MARKER}" in lines
    assert "affirmed:" not in text
    assert "commit:" not in text
    assert "adr:" not in text


def test_full_render_lists_every_field() -> None:
    record = _record(
        falsifier="A customer is charged early",
        rejected=[{"option": "Per request", "reason": "Breaks batch discount"}, {"option": "Cron"}],
        assumptions=["Invoices are mutable"],
        evidence=[
            {"kind": "test", "ref": "tests/test_close.py::test_daily", "exit_code": 0},
            {"kind": "note", "ref": "Checked with finance"},
        ],
        constraints=["Keep the API shape"],
        risks=["No lock"],
        links=[
            {"path": "src/a.py", "start_line": 80, "end_line": 140},
            {"path": "src/b.py", "start_line": 7, "end_line": 7},
            {"path": "src/c.py", "start_line": None, "end_line": None},
            {"path": "src/d.py", "start_line": 3, "end_line": None},
        ],
        adr="docs/decisions/0042.md",
        author={"kind": "agent", "name": "Bot", "tool": "claude-code"},
        **AFFIRMED,
    )
    text = render_record(record, commit="abc1234")
    assert text.splitlines()[0] == BANNER_AFFIRMED
    expected = [
        "falsifier: A customer is charged early",
        "rejected:\n  - Per request — Breaks batch discount\n  - Cron",
        "assumptions:\n  - Invoices are mutable",
        "evidence:\n  - test: tests/test_close.py::test_daily (exit 0)\n"
        "  - note: Checked with finance",
        "constraints:\n  - Keep the API shape",
        "risks:\n  - No lock",
        "links:\n  - src/a.py:80-140\n  - src/b.py:7\n  - src/c.py\n  - src/d.py:3",
        "adr: docs/decisions/0042.md",
        "author: agent Bot via claude-code",
        "created: 2026-10-15T13:00:01Z",
        "affirmed: 2026-10-16T09:00:00Z by Ada",
        "commit: abc1234",
    ]
    for chunk in expected:
        assert chunk in text, chunk


def test_human_author_without_name() -> None:
    text = render_record(_record(author={"kind": "human", "name": None, "tool": None}))
    assert "author: human\n" in text


def test_list_line_has_status_id_date_goal() -> None:
    line = render_list_line(_record(3))
    assert line.startswith("DRAFT     ")
    assert str(uuid7(3)) in line
    assert "2026-10-15" in line
    assert line.endswith("Goal number 3")
    assert render_list_line(_record(**AFFIRMED)).startswith("AFFIRMED  ")


def test_list_line_truncates_long_goal_and_flattens_whitespace() -> None:
    line = render_list_line(_record(goal="word " * 100))
    assert len(line) <= LIST_WIDTH
    assert line.endswith("…")
    assert "\n" not in render_list_line(_record(goal="two\nlines"))


# --- filtering and ordering ----------------------------------------------------------------


def _at(n: int, hour: int, **overrides: Any) -> Record:
    when = datetime(2026, 10, 15, hour, 0, 0, tzinfo=UTC)
    return _record(n, created_at=when, updated_at=when, **overrides)


def test_newest_first_with_id_tiebreak() -> None:
    records = [_at(1, 9), _at(2, 11), _at(3, 11), _at(4, 10)]
    assert [r.id for r in filter_records(records)] == [uuid7(3), uuid7(2), uuid7(4), uuid7(1)]


def test_filter_by_status_and_author() -> None:
    records = [
        _record(1),
        _record(2, **AFFIRMED),
        _record(3, author={"kind": "agent", "tool": "codex"}),
    ]
    assert {r.id for r in filter_records(records, status="affirmed")} == {uuid7(2)}
    assert {r.id for r in filter_records(records, status="draft")} == {uuid7(1), uuid7(3)}
    assert {r.id for r in filter_records(records, author_kind="agent")} == {uuid7(3)}
    assert filter_records(records, status="affirmed", author_kind="agent") == []


def test_filter_by_path_prefix_matches_any_link() -> None:
    records = [
        _record(1, links=[{"path": "src/billing/close.py"}]),
        _record(2, links=[{"path": "docs/a.md"}, {"path": "src/billing/models.py"}]),
        _record(3, links=[{"path": "tests/test_x.py"}]),
    ]
    assert {r.id for r in filter_records(records, path_prefix="src/billing")} == {
        uuid7(1),
        uuid7(2),
    }
    assert {r.id for r in filter_records(records, path_prefix="./tests/")} == {uuid7(3)}
    assert filter_records(records, path_prefix="lib/") == []
