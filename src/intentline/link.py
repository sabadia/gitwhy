"""Link a record to a commit: via ``.intentline/pending`` or by amending HEAD (docs/03 section 4).

Amending rewrites a commit, so it is refused whenever it could rewrite published history or
whenever intentline cannot be sure it is safe (CLAUDE.md: never rewrite published history).
"""

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from intentline.errors import UnsafeGitError, UsageError
from intentline.gitio import (
    add_intentline_trailer,
    amend_head_message,
    commit_message,
    current_branch,
    head_commit,
    intentline_ids,
    operation_in_progress,
    remote_refs_containing,
)
from intentline.store import INTENTLINE_DIRNAME, RecordStore, read_pending, write_pending


@dataclass(frozen=True)
class LinkResult:
    """What ``link`` did. ``amended`` is the new HEAD sha when HEAD was amended."""

    record_id: UUID
    pending: bool
    replaced_pending: UUID | None = None
    amended: str | None = None
    already_linked: bool = False


def link_pending(root: Path, record_id: UUID | str) -> LinkResult:
    """Write ``record_id`` to ``.intentline/pending`` so the next commit carries its trailer."""
    store = RecordStore(root / INTENTLINE_DIRNAME)
    record = store.load(record_id)
    previous = read_pending(store.intentline_dir)
    write_pending(store.intentline_dir, record.id)
    replaced = previous if previous is not None and previous != record.id else None
    return LinkResult(record_id=record.id, pending=True, replaced_pending=replaced)


def ensure_head_amendable(root: Path) -> str:
    """Return HEAD's sha if amending it is safe, else raise.

    Refuses (exit 7) on a detached HEAD, during a merge/rebase/cherry-pick/revert/bisect, or
    when any remote-tracking ref already contains HEAD. With no commits there is nothing to
    amend (exit 1).
    """
    head = head_commit(root)
    if head is None:
        raise UsageError(
            "There is no commit to amend yet.", hint="Commit first, or run `intentline link <id>`."
        )
    if current_branch(root) is None:
        raise UnsafeGitError(
            f"Refusing to amend: HEAD ({head[:12]}) is detached.",
            hint="Check out a branch, or run `intentline link <id>` for the next commit instead.",
        )
    operation = operation_in_progress(root)
    if operation is not None:
        raise UnsafeGitError(
            f"Refusing to amend while {operation} is in progress.",
            hint="Finish or abort it first.",
        )
    published = remote_refs_containing(head, root)
    if published:
        raise UnsafeGitError(
            f"Refusing to amend: HEAD ({head[:12]}) is already on {', '.join(published)}. "
            "Amending would rewrite published history.",
            hint="Run `intentline link <id>` so your next commit carries the trailer instead.",
        )
    return head


def link_amend_head(root: Path, record_id: UUID | str) -> LinkResult:
    """Add ``Intentline-Id: <id>`` to HEAD's message, if that is safe and HEAD is not linked yet.

    The record must exist. HEAD already linked to this record is a no-op; HEAD linked to a
    different record is refused, since an existing link is never replaced.
    """
    record = RecordStore(root / INTENTLINE_DIRNAME).load(record_id)
    head = ensure_head_amendable(root)
    message = commit_message(head, root)
    existing = intentline_ids(message, root)
    if record.id in existing:
        return LinkResult(record_id=record.id, pending=False, already_linked=True, amended=None)
    if existing:
        raise UsageError(
            f"HEAD ({head[:12]}) is already linked to record {existing[0]}; "
            "intentline never replaces an existing link.",
            hint="Run `intentline link <id>` to link the next commit instead.",
        )
    new_head = amend_head_message(add_intentline_trailer(message, record.id, root), root)
    return LinkResult(record_id=record.id, pending=False, amended=new_head)
