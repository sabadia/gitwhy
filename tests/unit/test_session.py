"""Reading goal candidates from session logs without inventing anything (docs/03 section 4)."""

import json
from pathlib import Path

import pytest

from intentline.errors import NotFoundError, UsageError
from intentline.session import (
    GOAL_MAX_LENGTH,
    SessionFacts,
    parse_session,
    read_session,
    session_files_in_repo,
    session_source_ref,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "sessions"


# --- the four shapes ---------------------------------------------------------------------------


def test_json_messages_object_uses_first_user_message_and_files() -> None:
    facts = read_session(FIXTURES / "messages.json")
    assert facts == SessionFacts(
        goal="Close invoices at end of day, not per request.",
        files=("src/billing/close.py", "/nowhere/outside.py"),
    )


def test_json_array_joins_text_parts_and_ignores_others() -> None:
    facts = read_session(FIXTURES / "array.json")
    assert facts == SessionFacts(goal="Retry on 429 but not on 500.", files=())


def test_claude_jsonl_skips_text_free_user_entries_and_reads_files() -> None:
    facts = read_session(FIXTURES / "claude.jsonl")
    assert facts == SessionFacts(
        goal="Make the daily close idempotent", files=("src/billing/close.py",)
    )


def test_plain_text_uses_first_non_empty_line() -> None:
    facts = read_session(FIXTURES / "plain.txt")
    assert facts == SessionFacts(goal="Add a daily close job for invoices", files=())


# --- what a session can never supply ------------------------------------------------------------


@pytest.mark.parametrize("name", ["messages.json", "array.json", "claude.jsonl", "plain.txt"])
def test_only_goal_and_files_are_ever_extracted(name: str) -> None:
    facts = read_session(FIXTURES / name)
    assert set(vars(facts)) == {"goal", "files"}


# --- edge cases -------------------------------------------------------------------------------


def test_assistant_messages_before_the_user_are_skipped() -> None:
    text = json.dumps(
        [{"role": "assistant", "content": "first"}, {"role": "user", "content": "second"}]
    )
    assert parse_session(text).goal == "second"


def test_long_goal_is_truncated_to_the_schema_limit() -> None:
    text = json.dumps({"messages": [{"role": "user", "content": "word " * 300}]})
    goal = parse_session(text).goal
    assert goal is not None
    assert len(goal) == GOAL_MAX_LENGTH
    assert goal.endswith("…")


def test_goal_at_the_limit_is_kept_whole() -> None:
    text = "x" * GOAL_MAX_LENGTH
    assert parse_session(text).goal == text


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   \n\n  ",
        json.dumps({"messages": [{"role": "assistant", "content": "only the agent spoke"}]}),
        json.dumps([{"role": "user", "content": [{"type": "tool_result", "content": "x"}]}]),
        json.dumps([{"role": "user", "content": 42}, "not a message"]),
        json.dumps({"role": "user", "message": "no messages key"}, indent=2),
        "null",
        "42",
        '"just a string"',
    ],
)
def test_no_usable_goal(text: str) -> None:
    assert parse_session(text).goal is None


def test_single_line_json_object_is_jsonl() -> None:
    assert parse_session('{"role": "user", "content": "one line"}').goal == "one line"


def test_jsonl_tolerates_blank_lines() -> None:
    text = '{"type": "summary"}\n\n   \n{"role": "user", "content": "after blanks"}\n'
    assert parse_session(text).goal == "after blanks"


def test_jsonl_with_a_non_object_line_is_plain_text() -> None:
    text = '{"role": "user", "content": "x"}\n[1, 2]\n'
    assert parse_session(text).goal == '{"role": "user", "content": "x"}'


def test_files_must_be_a_list_of_non_empty_strings() -> None:
    assert parse_session(json.dumps({"messages": [], "files": "a.py"})).files == ()
    assert parse_session(json.dumps({"messages": [], "files": ["a.py", 3, " ", ""]})).files == (
        "a.py",
    )


def test_wrapped_user_message_must_have_user_role() -> None:
    line = {"type": "user", "message": {"role": "assistant", "content": "not the user"}}
    assert parse_session(json.dumps(line)).goal is None


# --- reading files ------------------------------------------------------------------------------


def test_missing_session_file_is_not_found(tmp_path: Path) -> None:
    with pytest.raises(NotFoundError, match="does not exist"):
        read_session(tmp_path / "nope.jsonl")


def test_binary_session_file_is_a_usage_error(tmp_path: Path) -> None:
    path = tmp_path / "s.bin"
    path.write_bytes(b"\xff\xfe\x00\x81")
    with pytest.raises(UsageError, match="not UTF-8"):
        read_session(path)


def test_directory_is_a_usage_error(tmp_path: Path) -> None:
    with pytest.raises(UsageError, match="Cannot read session file"):
        read_session(tmp_path)


# --- repository helpers -------------------------------------------------------------------------


def test_source_ref_is_repo_relative_inside_the_repo(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    assert session_source_ref(root / "logs" / "s.jsonl", root) == "logs/s.jsonl"


def test_source_ref_is_name_only_outside_the_repo(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    outside = tmp_path / "home" / "someone" / ".claude" / "abc.jsonl"
    assert session_source_ref(outside, root) == "abc.jsonl"


def test_session_files_kept_inside_repo_only(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    files = ["src/a.py", str(root / "b.py"), "/elsewhere/c.py", "../d.py", "."]
    assert session_files_in_repo(files, root) == (str(root / "src/a.py"), str(root / "b.py"))
