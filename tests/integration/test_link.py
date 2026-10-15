"""``gitwhy link`` against real git repositories (docs/03 section 4, docs/05 section 2)."""

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from gitwhy.cli import app
from gitwhy.errors import UsageError
from gitwhy.gitio import (
    commit_message,
    current_branch,
    gitwhy_ids,
    head_commit,
    operation_in_progress,
    remote_refs_containing,
)
from gitwhy.store import RecordStore, initialize, read_pending
from tests.conftest import MakeRecord, plain, uuid7

runner = CliRunner()


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(  # noqa: S603
        ["git", "-C", str(repo), *args],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _commit(repo: Path, name: str, message: str) -> str:
    (repo / name).write_text(f"{name}\n", encoding="utf-8")
    _git(repo, "add", "--", name)
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(git_repo: Path, make_record: MakeRecord) -> Path:
    """An initialized repo with an identity, records 1 and 2, and one commit."""
    _git(git_repo, "config", "user.name", "Test Human")
    _git(git_repo, "config", "user.email", "test@example.com")
    _git(git_repo, "config", "commit.gpgsign", "false")
    initialize(git_repo)
    store = RecordStore(git_repo / ".gitwhy")
    store.save(make_record(1))
    store.save(make_record(2))
    _commit(git_repo, "a.py", "Add a\n\nExplain a.")
    return git_repo


@pytest.fixture
def pushed(repo: Path, tmp_path: Path) -> Path:
    """``repo`` with HEAD pushed to a local bare remote named origin."""
    remote = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)  # noqa: S603, S607
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "push", "-q", "origin", "HEAD:refs/heads/main")
    _git(repo, "fetch", "-q", "origin")
    return repo


def _link(repo: Path, monkeypatch: pytest.MonkeyPatch, *args: str) -> Result:
    monkeypatch.chdir(repo)
    return runner.invoke(app, ["link", *args])


# --- pending (default) ------------------------------------------------------------------------


def test_link_writes_pending(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _link(repo, monkeypatch, str(uuid7(1)))
    assert result.exit_code == 0, result.output
    assert (repo / ".gitwhy" / "pending").read_text() == f"{uuid7(1)}\n"
    assert "Linked" in plain(result.output)


def test_link_reports_replaced_pending(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _link(repo, monkeypatch, str(uuid7(1)))
    result = _link(repo, monkeypatch, str(uuid7(2)), "--json")
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data == {
        "id": str(uuid7(2)),
        "pending": True,
        "amended": None,
        "already_linked": False,
        "replaced_pending": str(uuid7(1)),
    }
    assert read_pending(repo / ".gitwhy") == uuid7(2)


def test_link_says_which_pending_record_it_replaced(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _link(repo, monkeypatch, str(uuid7(1)))
    result = _link(repo, monkeypatch, str(uuid7(2)))
    assert f"replaced the previously pending record {uuid7(1)}" in plain(result.output)


def test_relinking_same_id_is_not_a_replacement(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _link(repo, monkeypatch, str(uuid7(1)))
    result = _link(repo, monkeypatch, str(uuid7(1)))
    assert "replaced" not in plain(result.output)


def test_link_unknown_id_exits_9_and_writes_nothing(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _link(repo, monkeypatch, str(uuid7(99)))
    assert result.exit_code == 9
    assert not (repo / ".gitwhy" / "pending").exists()


def test_link_malformed_id_exits_1(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert _link(repo, monkeypatch, "../../etc/passwd").exit_code == 1


def test_link_outside_repo_exits_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plain_dir = tmp_path / "plain"
    plain_dir.mkdir()
    assert _link(plain_dir, monkeypatch, str(uuid7(1))).exit_code == 2


def test_link_before_init_exits_2(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert _link(git_repo, monkeypatch, str(uuid7(1))).exit_code == 2


# --- --amend-head -----------------------------------------------------------------------------


def test_amend_head_adds_trailer_and_keeps_message(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _git(repo, "rev-parse", "HEAD")
    author_before = _git(repo, "log", "-1", "--format=%an <%ae> %ad")
    result = _link(repo, monkeypatch, str(uuid7(1)), "--amend-head")
    assert result.exit_code == 0, result.output
    after = _git(repo, "rev-parse", "HEAD")
    assert after != before
    message = commit_message("HEAD", repo)
    assert message == f"Add a\n\nExplain a.\n\nGitwhy-Id: {uuid7(1)}\n"
    raw = _git(repo, "cat-file", "commit", "HEAD")
    assert raw.endswith(f"Gitwhy-Id: {uuid7(1)}"), "no trailing blank lines in the object"
    assert gitwhy_ids(message, repo) == [uuid7(1)]
    assert _git(repo, "log", "-1", "--format=%an <%ae> %ad") == author_before
    assert not (repo / ".gitwhy" / "pending").exists()
    assert f"Amended HEAD ({after[:12]})" in plain(result.output)


def test_amend_head_does_not_include_staged_changes(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files_before = _git(repo, "show", "--name-only", "--format=", "HEAD")
    (repo / "staged.py").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "staged.py")
    assert _link(repo, monkeypatch, str(uuid7(1)), "--amend-head").exit_code == 0
    assert _git(repo, "show", "--name-only", "--format=", "HEAD") == files_before
    assert _git(repo, "diff", "--cached", "--name-only") == "staged.py"


def test_amend_head_keeps_existing_signoff(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _commit(repo, "b.py", "Add b\n\nSigned-off-by: Test Human <test@example.com>")
    assert _link(repo, monkeypatch, str(uuid7(1)), "--amend-head").exit_code == 0
    assert commit_message("HEAD", repo).endswith(
        f"Signed-off-by: Test Human <test@example.com>\nGitwhy-Id: {uuid7(1)}\n"
    )


def test_amend_head_on_pushed_commit_exits_7(pushed: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    before = _git(pushed, "rev-parse", "HEAD")
    message_before = commit_message("HEAD", pushed)
    result = _link(pushed, monkeypatch, str(uuid7(1)), "--amend-head")
    assert result.exit_code == 7, result.output
    assert "refs/remotes/origin/main" in plain(result.output)
    assert "published history" in plain(result.output)
    assert _git(pushed, "rev-parse", "HEAD") == before
    assert commit_message("HEAD", pushed) == message_before


def test_amend_head_after_new_local_commit_is_allowed(
    pushed: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _commit(pushed, "b.py", "Add b")
    result = _link(pushed, monkeypatch, str(uuid7(1)), "--amend-head")
    assert result.exit_code == 0, result.output


def test_amend_head_on_detached_head_exits_7(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _git(repo, "checkout", "-q", "--detach")
    result = _link(repo, monkeypatch, str(uuid7(1)), "--amend-head")
    assert result.exit_code == 7
    assert "detached" in plain(result.output)


def test_amend_head_during_merge_exits_7(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = _git(repo, "branch", "--show-current")
    _git(repo, "checkout", "-q", "-b", "other")
    _commit(repo, "conflict.txt", "other side")
    _git(repo, "checkout", "-q", base)
    (repo / "conflict.txt").write_text("this side\n", encoding="utf-8")
    _git(repo, "add", "conflict.txt")
    _git(repo, "commit", "-q", "-m", "this side")
    subprocess.run(["git", "-C", str(repo), "merge", "-q", "other"], capture_output=True)  # noqa: S603, S607
    assert operation_in_progress(repo) == "a merge"
    result = _link(repo, monkeypatch, str(uuid7(1)), "--amend-head")
    assert result.exit_code == 7
    assert "merge is in progress" in plain(result.output)


def test_amend_head_with_no_commits_exits_1(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, make_record: MakeRecord
) -> None:
    initialize(git_repo)
    RecordStore(git_repo / ".gitwhy").save(make_record(1))
    result = _link(git_repo, monkeypatch, str(uuid7(1)), "--amend-head")
    assert result.exit_code == 1
    assert "no commit to amend" in plain(result.output)


def test_amend_head_already_linked_to_same_record_is_a_no_op(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _link(repo, monkeypatch, str(uuid7(1)), "--amend-head")
    before = _git(repo, "rev-parse", "HEAD")
    result = _link(repo, monkeypatch, str(uuid7(1)), "--amend-head")
    assert result.exit_code == 0
    assert "Nothing changed" in plain(result.output)
    assert _git(repo, "rev-parse", "HEAD") == before


def test_amend_head_never_replaces_another_link(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _link(repo, monkeypatch, str(uuid7(1)), "--amend-head")
    before = _git(repo, "rev-parse", "HEAD")
    result = _link(repo, monkeypatch, str(uuid7(2)), "--amend-head")
    assert result.exit_code == 1
    assert "never replaces an existing link" in plain(result.output)
    assert _git(repo, "rev-parse", "HEAD") == before


def test_amend_head_unknown_id_exits_9_and_leaves_head(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _git(repo, "rev-parse", "HEAD")
    assert _link(repo, monkeypatch, str(uuid7(99)), "--amend-head").exit_code == 9
    assert _git(repo, "rev-parse", "HEAD") == before


def test_amend_rejected_by_commit_msg_hook_leaves_head(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hook = repo / ".git" / "hooks" / "commit-msg"
    hook.write_text("#!/bin/sh\necho 'policy says no' >&2\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)
    before = _git(repo, "rev-parse", "HEAD")
    result = _link(repo, monkeypatch, str(uuid7(1)), "--amend-head")
    assert result.exit_code == 1
    assert "policy says no" in plain(result.output)
    assert _git(repo, "rev-parse", "HEAD") == before


def test_amend_head_json(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _link(repo, monkeypatch, str(uuid7(1)), "--amend-head", "--json")
    data = json.loads(result.stdout)
    assert data["amended"] == _git(repo, "rev-parse", "HEAD")
    assert data["pending"] is False


# --- git primitives ---------------------------------------------------------------------------


def test_head_and_branch_on_unborn_repo(git_repo: Path) -> None:
    assert head_commit(git_repo) is None
    assert current_branch(git_repo) is not None  # unborn branch is still a branch


def test_commit_message_of_unknown_rev(repo: Path) -> None:
    with pytest.raises(UsageError, match="Cannot read commit"):
        commit_message("no-such-rev", repo)


def test_remote_refs_failure_is_reported(repo: Path) -> None:
    with pytest.raises(UsageError, match="git for-each-ref failed"):
        remote_refs_containing("no-such-rev", repo)


def test_read_pending_tolerates_bad_content(tmp_path: Path) -> None:
    gitwhy = tmp_path / ".gitwhy"
    gitwhy.mkdir()
    assert read_pending(gitwhy) is None
    for content in (b"", b"not-a-uuid\n", b"\xff\xfe"):
        (gitwhy / "pending").write_bytes(content)
        assert read_pending(gitwhy) is None
    (gitwhy / "pending").write_text(f"  {uuid7(3)}  \n", encoding="utf-8")
    assert read_pending(gitwhy) == uuid7(3)
