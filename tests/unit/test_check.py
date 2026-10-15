"""The pure check decision, ignore matching, and numstat parsing (docs/02 section 4.5)."""

import pytest

from intentline.check import Verdict, decide, is_ignored
from intentline.gitio import FileChange, _parse_numstat
from intentline.models import DEFAULT_CHECK_IGNORE
from tests.conftest import uuid7

IGNORE = list(DEFAULT_CHECK_IGNORE)


@pytest.mark.parametrize(
    ("path", "ignored"),
    [
        ("uv.lock", True),
        ("sub/uv.lock", True),  # pattern without '/' matches the name anywhere
        ("Cargo.lock", True),
        ("deep/dir/yarn.lock", True),
        (".intentline/records/x.yml", True),
        (".intentline/config.yml", True),
        ("schema/record.schema.json", True),
        ("src/api_generated.py", True),
        ("src/app.py", False),
        ("lockfile.py", False),
        ("docs/schema/notes.md", False),  # 'schema/**' is anchored at the repo root
        ("package-lock.json", True),
    ],
)
def test_default_ignore_patterns(path: str, ignored: bool) -> None:
    assert is_ignored(path, IGNORE) is ignored


def test_no_patterns_ignore_nothing() -> None:
    assert is_ignored("uv.lock", []) is False


def _changes(*items: tuple[str, int]) -> list[FileChange]:
    return [FileChange(path=path, added=lines, deleted=0) for path, lines in items]


def test_under_threshold_passes() -> None:
    result = decide(_changes(("a.py", 29)), ignore=IGNORE, min_lines=30, linked_ids=[])
    assert result.verdict is Verdict.UNDER_THRESHOLD and result.ok
    assert result.changed_lines == 29


def test_at_threshold_without_record_fails() -> None:
    result = decide(_changes(("a.py", 30)), ignore=IGNORE, min_lines=30, linked_ids=[])
    assert result.verdict is Verdict.NEEDS_RECORD and not result.ok


def test_over_threshold_with_record_passes() -> None:
    result = decide(_changes(("a.py", 300)), ignore=IGNORE, min_lines=30, linked_ids=[uuid7(1)])
    assert result.verdict is Verdict.LINKED and result.ok
    assert result.linked_ids == [uuid7(1)]


def test_ignored_files_do_not_count() -> None:
    result = decide(
        _changes(("uv.lock", 900), ("src/app.py", 5)), ignore=IGNORE, min_lines=30, linked_ids=[]
    )
    assert result.verdict is Verdict.UNDER_THRESHOLD
    assert result.changed_lines == 5
    assert result.counted == ["src/app.py"]
    assert result.ignored == ["uv.lock"]


def test_only_ignored_files_pass() -> None:
    result = decide(_changes(("uv.lock", 900)), ignore=IGNORE, min_lines=30, linked_ids=[])
    assert result.ok and result.changed_lines == 0


def test_deleted_lines_count() -> None:
    changes = [FileChange(path="a.py", added=10, deleted=25)]
    assert decide(changes, ignore=[], min_lines=30, linked_ids=[]).changed_lines == 35


def test_zero_threshold_requires_a_record_for_any_change() -> None:
    assert not decide([], ignore=[], min_lines=0, linked_ids=[]).ok


def test_parse_numstat_handles_binary_rename_and_spaces() -> None:
    output = "3\t0\tadd.py\x00-\t-\tb.bin\x001\t0\t\x00old.py\x00new name.py\x00"
    assert _parse_numstat(output) == [
        FileChange(path="add.py", added=3, deleted=0),
        FileChange(path="b.bin", added=0, deleted=0, binary=True),
        FileChange(path="new name.py", added=1, deleted=0),
    ]


def test_parse_numstat_empty() -> None:
    assert _parse_numstat("") == []
