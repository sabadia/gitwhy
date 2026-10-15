"""Find the records that explain a line or a commit (docs/02 section 4.4).

Two sources, both local:

1. Commits that changed the line (``git log -L``) and their ``Whyline-Id`` trailers.
2. Records whose links name the file and a line range covering the line (or the whole file),
   which also finds records written before their commit exists.

Results are newest first. Unless ``all_records`` is set, they stop at the first affirmed
record: drafts newer than it are still shown, because a draft is a claim worth seeing, but
older ones are hidden behind the confirmed reason.
"""

from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from whyline.capture import resolve_files
from whyline.errors import NotFoundError, UsageError, WhylineError
from whyline.gitio import commit_links, head_commit, is_shallow, line_history
from whyline.models import StoredRecord
from whyline.store import WHYLINE_DIRNAME, RecordStore


@dataclass(frozen=True)
class Location:
    """A repo-relative path and a 1-based line."""

    path: str
    line: int


@dataclass
class Explanation:
    """One record that explains the query, and the commits that link to it."""

    record: StoredRecord
    commits: list[str] = field(default_factory=list)
    via_link: bool = False


@dataclass
class RecallResult:
    """What ``why`` found. ``missing`` are trailer ids with no record file."""

    explanations: list[Explanation] = field(default_factory=list)
    missing: list[UUID] = field(default_factory=list)
    hidden: int = 0
    no_commits: bool = False
    shallow: bool = False
    skipped: list[WhylineError] = field(default_factory=list)


def parse_location(spec: str, *, cwd: Path, root: Path) -> Location:
    """Parse ``path:line`` (path relative to ``cwd``) into a repo-relative ``Location``."""
    path, sep, line_text = spec.rpartition(":")
    if not sep or not path:
        raise UsageError(
            f"Expected FILE:LINE, got {spec!r}.", hint="For example: whyline why src/app.py:40"
        )
    try:
        line = int(line_text)
    except ValueError:
        raise UsageError(
            f"{line_text!r} is not a line number in {spec!r}.",
            hint="For example: whyline why src/app.py:40",
        ) from None
    if line < 1:
        raise UsageError(f"Line numbers start at 1, got {line}.")
    (resolved,) = resolve_files([path], cwd=cwd, root=root)
    return Location(path=resolved, line=line)


def _covers(record: StoredRecord, location: Location) -> bool:
    for link in record.links:
        if link.path != location.path:
            continue
        start = link.start_line if link.start_line is not None else link.end_line
        end = link.end_line if link.end_line is not None else link.start_line
        if start is None or end is None or start <= location.line <= end:
            return True
    return False


def _finish(
    found: dict[UUID, Explanation], result: RecallResult, *, all_records: bool
) -> RecallResult:
    ordered = sorted(found.values(), key=lambda e: (e.record.created_at, e.record.id), reverse=True)
    if not all_records:
        for index, explanation in enumerate(ordered):
            if explanation.record.status == "affirmed":
                result.hidden = len(ordered) - index - 1
                ordered = ordered[: index + 1]
                break
    result.explanations = ordered
    return result


def _load_linked(
    store: RecordStore,
    record_id: UUID,
    sha: str,
    found: dict[UUID, Explanation],
    result: RecallResult,
) -> None:
    if record_id in found:
        if sha not in found[record_id].commits:
            found[record_id].commits.append(sha)
        return
    try:
        found[record_id] = Explanation(record=store.load(record_id), commits=[sha])
    except NotFoundError:
        if record_id not in result.missing:
            result.missing.append(record_id)
    except WhylineError as exc:
        result.skipped.append(exc)


def why_line(root: Path, location: Location, *, all_records: bool = False) -> RecallResult:
    """Return the records that explain ``location``."""
    store = RecordStore(root / WHYLINE_DIRNAME)
    store.require_initialized()
    result = RecallResult(no_commits=head_commit(root) is None, shallow=is_shallow(root))
    found: dict[UUID, Explanation] = {}
    for commit in line_history(root, location.path, location.line):
        for record_id in commit.record_ids:
            _load_linked(store, record_id, commit.sha, found, result)
    listing = store.mentioning(location.path)
    result.skipped.extend(listing.errors)
    for record in listing.records:
        if record.id not in found and _covers(record, location):
            found[record.id] = Explanation(record=record, via_link=True)
    return _finish(found, result, all_records=all_records)


def why_commit(root: Path, rev: str, *, all_records: bool = True) -> RecallResult:
    """Return the records linked to commit ``rev`` by ``Whyline-Id`` trailers."""
    store = RecordStore(root / WHYLINE_DIRNAME)
    store.require_initialized()
    commit = commit_links(root, rev)
    if commit is None:
        raise NotFoundError(f"No commit {rev!r} in this repository.", hint="Check the sha.")
    result = RecallResult(shallow=is_shallow(root))
    found: dict[UUID, Explanation] = {}
    for record_id in commit.record_ids:
        _load_linked(store, record_id, commit.sha, found, result)
    return _finish(found, result, all_records=all_records)
