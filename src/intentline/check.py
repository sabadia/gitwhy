"""Decide whether a change needs a record (docs/02 section 4.5, docs/03 section 4).

``intentline check`` never modifies the repository. It counts the changed lines of the staged
diff (or a commit range), leaving out files matched by ``check.ignore``. A change under
``check.min_lines`` passes. A larger change passes only if it is linked to a record: an id in
``.intentline/pending``, or a ``Intentline-Id`` trailer on HEAD (staged mode) or on any commit in
the range.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath
from uuid import UUID

from intentline.config import load_config
from intentline.errors import UsageError
from intentline.gitio import FileChange, commit_links, diff_numstat, head_commit, range_record_ids
from intentline.store import INTENTLINE_DIRNAME, RecordStore, read_pending

CAPTURE_COMMAND = 'intentline capture --goal "what this change is for" --pending'


class Verdict(StrEnum):
    """Why ``check`` passed or failed."""

    UNDER_THRESHOLD = "under_threshold"
    LINKED = "linked"
    NEEDS_RECORD = "needs_record"


@dataclass(frozen=True)
class CheckResult:
    """The decision and the numbers behind it."""

    verdict: Verdict
    changed_lines: int
    min_lines: int
    counted: list[str] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)
    linked_ids: list[UUID] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True unless the change needs a record."""
        return self.verdict is not Verdict.NEEDS_RECORD


def is_ignored(path: str, patterns: Sequence[str]) -> bool:
    """Return True if ``path`` matches any ignore pattern.

    Patterns use shell-style wildcards against the repo-relative path, where ``*`` also
    matches ``/`` (so ``.intentline/**`` covers everything under ``.intentline/``).
    A pattern with no
    ``/`` also matches the file name in any directory, as in ``.gitignore``.
    """
    name = PurePosixPath(path).name
    return any(
        fnmatchcase(path, pattern) or ("/" not in pattern and fnmatchcase(name, pattern))
        for pattern in patterns
    )


def decide(
    changes: Sequence[FileChange],
    *,
    ignore: Sequence[str],
    min_lines: int,
    linked_ids: Sequence[UUID],
) -> CheckResult:
    """Return the verdict for ``changes``. Pure: no git, no files."""
    counted = [c for c in changes if not is_ignored(c.path, ignore)]
    ignored = [c.path for c in changes if is_ignored(c.path, ignore)]
    lines = sum(c.lines for c in counted)
    if lines < min_lines:
        verdict = Verdict.UNDER_THRESHOLD
    elif linked_ids:
        verdict = Verdict.LINKED
    else:
        verdict = Verdict.NEEDS_RECORD
    return CheckResult(
        verdict=verdict,
        changed_lines=lines,
        min_lines=min_lines,
        counted=[c.path for c in counted],
        ignored=ignored,
        linked_ids=list(linked_ids),
    )


def _linked_ids(root: Path, rev_range: str | None) -> list[UUID]:
    ids: list[UUID] = []
    pending = read_pending(root / INTENTLINE_DIRNAME)
    if pending is not None:
        ids.append(pending)
    if rev_range is None:
        if head_commit(root) is not None:
            head = commit_links(root, "HEAD")
            ids.extend(head.record_ids if head is not None else ())
    else:
        ids.extend(range_record_ids(root, rev_range))
    return list(dict.fromkeys(ids))


def run_check(
    root: Path, *, rev_range: str | None = None, min_lines: int | None = None
) -> CheckResult:
    """Check the staged diff (or ``rev_range``, e.g. ``main..HEAD``) of the repo at ``root``."""
    RecordStore(root / INTENTLINE_DIRNAME).require_initialized()
    if rev_range is not None and ".." not in rev_range:
        raise UsageError(
            f"--range needs two ends, got {rev_range!r}.", hint="For example: --range main..HEAD"
        )
    if min_lines is not None and min_lines < 0:
        raise UsageError(f"--min-lines must be 0 or more, got {min_lines}.")
    config = load_config(root).check
    threshold = config.min_lines if min_lines is None else min_lines
    changes = diff_numstat(root, rev_range)
    return decide(
        changes,
        ignore=config.ignore,
        min_lines=threshold,
        linked_ids=_linked_ids(root, rev_range),
    )
