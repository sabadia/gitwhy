"""Local git queries. Only runs the local ``git`` binary; never touches the network."""

import shutil
import subprocess
from pathlib import Path
from uuid import UUID

from whyline.errors import NoRepoError, UsageError

WHYLINE_PREFIX = ".whyline/"

TRAILER_KEY = "Whyline-Id"
"""Commit trailer linking a commit to a record (docs/03 section 5). The only trailer v1 writes."""


def _git_executable() -> str:
    git = shutil.which("git")
    if git is None:
        raise NoRepoError(
            "git is not installed or not on PATH.", hint="Install git and run the command again."
        )
    return git


def repo_root(start: Path) -> Path:
    """Return the top-level directory of the git work tree containing ``start``."""
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell, local git only
        [_git_executable(), "rev-parse", "--show-toplevel"],
        cwd=start,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise NoRepoError(
            f"Not inside a git work tree: {start}.",
            hint="Run `git init` first, or run whyline inside a git repository.",
        )
    return Path(completed.stdout.strip())


def config_value(key: str, cwd: Path) -> str | None:
    """Return ``git config --get <key>`` as seen from ``cwd``, or None when it is unset."""
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell, local git only
        [_git_executable(), "config", "--get", key],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return value or None


def staged_paths(root: Path) -> list[str]:
    """Return repo-relative POSIX paths in the index that differ from HEAD.

    Works in a repository with no commits yet. Paths under ``.whyline/`` are left out: a record
    never explains whyline's own files.
    """
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell, local git only
        [_git_executable(), "diff", "--cached", "--name-only", "-z"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise NoRepoError(f"Cannot list staged files in {root}: {detail}.")
    try:
        names = completed.stdout.decode("utf-8")
    except UnicodeDecodeError:
        raise UsageError(
            "Some staged file names are not valid UTF-8.", hint="Pass the files with --file."
        ) from None
    return [
        name
        for name in names.split("\0")
        if name and name != WHYLINE_PREFIX.rstrip("/") and not name.startswith(WHYLINE_PREFIX)
    ]


# --- commit message trailers (docs/03 section 5) ------------------------------------------------


def _interpret_trailers(args: list[str], message: str, cwd: Path) -> str:
    """Run ``git interpret-trailers`` on ``message`` (stdin) and return its stdout."""
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell, local git only
        [_git_executable(), "interpret-trailers", *args],
        cwd=cwd,
        input=message,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise UsageError(
            f"git interpret-trailers failed: {completed.stderr.strip() or 'unknown error'}."
        )
    return completed.stdout


def parse_trailers(message: str, cwd: Path) -> list[tuple[str, str]]:
    """Return the ``(key, value)`` trailers git finds in ``message``, in order.

    Only the trailer block at the end of the message counts; a ``Key: value`` line in the body
    is not a trailer. Folded values are unfolded.
    """
    trailers: list[tuple[str, str]] = []
    for line in _interpret_trailers(["--parse"], message, cwd).splitlines():
        key, sep, value = line.partition(":")
        if sep:
            trailers.append((key.strip(), value.strip()))
    return trailers


def whyline_ids(message: str, cwd: Path) -> list[UUID]:
    """Return the record ids in ``message``'s ``Whyline-Id`` trailers, in order, without repeats.

    The key matches case-insensitively, as git does. Values that are not UUIDs are skipped:
    a malformed trailer links to nothing rather than failing the caller.
    """
    ids: list[UUID] = []
    for key, value in parse_trailers(message, cwd):
        if key.lower() != TRAILER_KEY.lower():
            continue
        try:
            record_id = UUID(value)
        except ValueError:
            continue
        if record_id not in ids:
            ids.append(record_id)
    return ids


def add_whyline_trailer(message: str, record_id: UUID, cwd: Path) -> str:
    """Return ``message`` with a ``Whyline-Id: <record_id>`` trailer.

    Git places it in the trailer block (after a blank line, before comment lines). If the
    message already has any ``Whyline-Id`` trailer, it is returned unchanged: one commit links
    one record, and an existing link is never replaced.
    """
    return _interpret_trailers(
        ["--if-exists", "doNothing", "--trailer", f"{TRAILER_KEY}: {record_id}"], message, cwd
    )


# --- HEAD inspection and message-only amend (docs/03 section 4, `whyline link`) ----------------


def _run_git(
    args: list[str], cwd: Path, *, stdin: str | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed argv, no shell, local git only
        [_git_executable(), *args],
        cwd=cwd,
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


def head_commit(cwd: Path) -> str | None:
    """Return the full sha of HEAD, or None if the branch has no commits yet."""
    completed = _run_git(["rev-parse", "--verify", "--quiet", "HEAD^{commit}"], cwd)
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def current_branch(cwd: Path) -> str | None:
    """Return the checked-out branch name, or None when HEAD is detached."""
    completed = _run_git(["symbolic-ref", "--quiet", "--short", "HEAD"], cwd)
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def remote_refs_containing(rev: str, cwd: Path) -> list[str]:
    """Return remote-tracking refs (``refs/remotes/...``) that already contain ``rev``.

    Uses only local refs, so it never touches the network. A non-empty result means the
    commit has been pushed (as far as this clone knows).
    """
    completed = _run_git(
        ["for-each-ref", "--contains", rev, "--format=%(refname)", "refs/remotes"], cwd
    )
    if completed.returncode != 0:
        raise UsageError(f"git for-each-ref failed: {completed.stderr.strip() or 'unknown error'}.")
    return [line for line in completed.stdout.splitlines() if line]


_IN_PROGRESS_MARKERS = (
    ("MERGE_HEAD", "a merge"),
    ("CHERRY_PICK_HEAD", "a cherry-pick"),
    ("REVERT_HEAD", "a revert"),
    ("rebase-merge", "a rebase"),
    ("rebase-apply", "a rebase or am"),
    ("BISECT_LOG", "a bisect"),
)


def operation_in_progress(cwd: Path) -> str | None:
    """Return a description of an unfinished merge, rebase, etc., or None if there is none."""
    for marker, description in _IN_PROGRESS_MARKERS:
        completed = _run_git(["rev-parse", "--git-path", marker], cwd)
        path = Path(completed.stdout.strip())
        if not path.is_absolute():
            path = cwd / path
        if completed.returncode == 0 and path.exists():
            return description
    return None


def commit_message(rev: str, cwd: Path) -> str:
    """Return the full message of commit ``rev``, ending in exactly one newline.

    ``--format=%B`` appends a newline of its own; it is dropped so a read-modify-amend cycle
    does not grow the message.
    """
    completed = _run_git(["log", "-1", "--format=%B", rev, "--"], cwd)
    if completed.returncode != 0:
        raise UsageError(f"Cannot read commit {rev}: {completed.stderr.strip()}.")
    return completed.stdout.rstrip("\n") + "\n"


def amend_head_message(message: str, cwd: Path) -> str:
    """Replace HEAD's message with ``message`` and return the new HEAD sha.

    ``--only`` with no paths changes the message alone: staged changes stay staged and out of
    the commit. ``--cleanup=verbatim`` keeps the message as given, except that trailing blank
    lines are dropped. Hooks still run.
    """
    completed = _run_git(
        ["commit", "--amend", "--only", "--cleanup=verbatim", "--file=-"],
        cwd,
        stdin=message.rstrip("\n") + "\n",
    )
    if completed.returncode != 0:
        raise UsageError(
            "git commit --amend failed; HEAD is unchanged: "
            f"{completed.stderr.strip() or completed.stdout.strip() or 'unknown error'}."
        )
    return _run_git(["rev-parse", "HEAD"], cwd).stdout.strip()
