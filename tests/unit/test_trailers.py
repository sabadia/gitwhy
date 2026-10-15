"""Gitwhy-Id trailer parsing and writing via ``git interpret-trailers`` (docs/03 section 5)."""

import subprocess
from pathlib import Path
from uuid import UUID

import pytest

from gitwhy.errors import NoRepoError, UsageError
from gitwhy.gitio import TRAILER_KEY, add_gitwhy_trailer, gitwhy_ids, parse_trailers
from tests.conftest import uuid7

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "commit_messages"
DOC_ID = UUID("01932a7e-5b1c-7c3a-8f21-9c0e4d2a1b77")


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# --- parsing ------------------------------------------------------------------------------------


def test_docs_example_message(tmp_path: Path) -> None:
    assert gitwhy_ids(_fixture("docs_example.txt"), tmp_path) == [DOC_ID]


def test_gitwhy_id_coexists_with_signed_off_by(tmp_path: Path) -> None:
    message = _fixture("with_signoff.txt")
    assert parse_trailers(message, tmp_path) == [
        ("Signed-off-by", "Ada Lovelace <ada@example.com>"),
        ("Gitwhy-Id", str(uuid7(2))),
        ("Co-authored-by", "Grace Hopper <grace@example.com>"),
    ]
    assert gitwhy_ids(message, tmp_path) == [uuid7(2)]


def test_lookalike_line_in_body_is_not_a_trailer(tmp_path: Path) -> None:
    assert gitwhy_ids(_fixture("body_lookalike.txt"), tmp_path) == []


@pytest.mark.parametrize("name", ["subject_only.txt", "with_comments.txt"])
def test_messages_without_trailers(tmp_path: Path, name: str) -> None:
    assert parse_trailers(_fixture(name), tmp_path) == []
    assert gitwhy_ids(_fixture(name), tmp_path) == []


def test_empty_message(tmp_path: Path) -> None:
    assert gitwhy_ids("", tmp_path) == []


def test_key_matches_case_insensitively(tmp_path: Path) -> None:
    assert gitwhy_ids(f"Subject\n\ngitwhy-id: {uuid7(4)}\n", tmp_path) == [uuid7(4)]


def test_multiple_ids_keep_order_without_repeats(tmp_path: Path) -> None:
    message = f"Subject\n\nGitwhy-Id: {uuid7(5)}\nGitwhy-Id: {uuid7(6)}\nGitwhy-Id: {uuid7(5)}\n"
    assert gitwhy_ids(message, tmp_path) == [uuid7(5), uuid7(6)]


def test_malformed_value_is_skipped(tmp_path: Path) -> None:
    message = f"Subject\n\nGitwhy-Id: not-a-uuid\nGitwhy-Id: {uuid7(7)}\n"
    assert gitwhy_ids(message, tmp_path) == [uuid7(7)]


def test_crlf_message(tmp_path: Path) -> None:
    message = f"Subject\r\n\r\nSigned-off-by: A <a@x>\r\nGitwhy-Id: {uuid7(8)}\r\n"
    assert gitwhy_ids(message, tmp_path) == [uuid7(8)]


def test_other_trailers_are_ignored(tmp_path: Path) -> None:
    message = f"Subject\n\nSigned-off-by: A <a@x>\nRefs: {uuid7(9)}\n"
    assert gitwhy_ids(message, tmp_path) == []


# --- writing ------------------------------------------------------------------------------------


def test_add_to_message_without_trailers(tmp_path: Path) -> None:
    result = add_gitwhy_trailer("Subject only\n", uuid7(1), tmp_path)
    assert result == f"Subject only\n\n{TRAILER_KEY}: {uuid7(1)}\n"


def test_add_joins_existing_trailer_block(tmp_path: Path) -> None:
    message = "Fix it\n\nBody.\n\nSigned-off-by: Ada <ada@example.com>\n"
    result = add_gitwhy_trailer(message, uuid7(1), tmp_path)
    assert result == (
        f"Fix it\n\nBody.\n\nSigned-off-by: Ada <ada@example.com>\n{TRAILER_KEY}: {uuid7(1)}\n"
    )
    assert parse_trailers(result, tmp_path)[0] == ("Signed-off-by", "Ada <ada@example.com>")


def test_add_keeps_commit_template_comments_last(tmp_path: Path) -> None:
    result = add_gitwhy_trailer(_fixture("with_comments.txt"), uuid7(1), tmp_path)
    assert gitwhy_ids(result, tmp_path) == [uuid7(1)]
    assert result.index(TRAILER_KEY) < result.index("# Please enter")


@pytest.mark.parametrize("existing_key", ["Gitwhy-Id", "gitwhy-id"])
def test_add_never_replaces_an_existing_link(tmp_path: Path, existing_key: str) -> None:
    message = f"Subject\n\n{existing_key}: {uuid7(1)}\n"
    assert add_gitwhy_trailer(message, uuid7(2), tmp_path) == message


def test_add_is_idempotent(tmp_path: Path) -> None:
    once = add_gitwhy_trailer("Subject\n", uuid7(1), tmp_path)
    assert add_gitwhy_trailer(once, uuid7(1), tmp_path) == once


def test_existing_malformed_link_is_kept_not_replaced(tmp_path: Path) -> None:
    message = "Subject\n\nGitwhy-Id: not-a-uuid\n"
    result = add_gitwhy_trailer(message, uuid7(3), tmp_path)
    assert result == message
    assert gitwhy_ids(result, tmp_path) == []


# --- failures -----------------------------------------------------------------------------------


def test_git_failure_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=128, stdout="", stderr="fatal: boom")

    monkeypatch.setattr("gitwhy.gitio.subprocess.run", failing_run)
    with pytest.raises(UsageError, match="git interpret-trailers failed: fatal: boom"):
        parse_trailers("Subject\n", tmp_path)


def test_git_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("gitwhy.gitio.shutil.which", lambda name: None)
    with pytest.raises(NoRepoError, match="git is not installed"):
        gitwhy_ids("Subject\n", tmp_path)
