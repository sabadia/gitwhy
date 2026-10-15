"""Human-readable rendering of records, plus filtering and ordering for ``intentline list``."""

from collections.abc import Iterable, Sequence

from intentline.models import AuthorKind, Record, RecordStatus, StoredRecord

AnyRecord = Record | StoredRecord

BANNER_AFFIRMED = "AFFIRMED"
BANNER_DRAFT = "DRAFT — not a confirmed reason"
NONE_MARKER = "(none)"
"""Shown for an empty narrative field, so a gap stays visible instead of disappearing."""

LIST_WIDTH = 100
_STATUS_TAGS = {"affirmed": "AFFIRMED", "draft": "DRAFT"}
_TAG_WIDTH = max(len(tag) for tag in _STATUS_TAGS.values())


def banner(record: AnyRecord) -> str:
    """Return the status banner. Drafts are always labelled as unconfirmed claims."""
    return BANNER_AFFIRMED if record.status == "affirmed" else BANNER_DRAFT


def _section(title: str, items: Sequence[str]) -> list[str]:
    if not items:
        return [f"{title}: {NONE_MARKER}"]
    return [f"{title}:", *(f"  - {item}" for item in items)]


def _link(path: str, start: int | None, end: int | None) -> str:
    if start is None and end is None:
        return path
    if start is not None and end is not None and start != end:
        return f"{path}:{start}-{end}"
    return f"{path}:{start if start is not None else end}"


def render_record(record: AnyRecord, *, commit: str | None = None) -> str:
    """Render one record for a terminal. Every narrative field is shown, empty or not."""
    rejected = [f"{r.option} — {r.reason}" if r.reason else r.option for r in record.rejected]
    evidence = [
        f"{e.kind}: {e.ref}" + ("" if e.exit_code is None else f" (exit {e.exit_code})")
        for e in record.evidence
    ]
    author: str = record.author.kind
    if record.author.name:
        author += f" {record.author.name}"
    if record.author.tool:
        author += f" via {record.author.tool}"

    lines = [
        banner(record),
        f"id: {record.id}",
        f"goal: {record.goal}",
        f"falsifier: {record.falsifier or NONE_MARKER}",
        *_section("rejected", rejected),
        *_section("assumptions", record.assumptions),
        *_section("evidence", evidence),
        *_section("constraints", record.constraints),
        *_section("risks", record.risks),
        *_section("links", [_link(k.path, k.start_line, k.end_line) for k in record.links]),
    ]
    if record.adr:
        lines.append(f"adr: {record.adr}")
    lines.append(f"author: {author}")
    lines.append(f"created: {_timestamp(record)}")
    if record.affirmed_at is not None:
        lines.append(f"affirmed: {record.affirmed_at:%Y-%m-%dT%H:%M:%SZ} by {record.affirmed_by}")
    if commit:
        lines.append(f"commit: {commit}")
    return "\n".join(lines)


def _timestamp(record: AnyRecord) -> str:
    return f"{record.created_at:%Y-%m-%dT%H:%M:%SZ}"


def render_list_line(record: AnyRecord) -> str:
    """Render one record as a single line: status tag, id, date, and the goal, fitted to width."""
    prefix = (
        f"{_STATUS_TAGS[record.status]:<{_TAG_WIDTH}}  {record.id}  {record.created_at:%Y-%m-%d}  "
    )
    room = max(LIST_WIDTH - len(prefix), 10)
    goal = " ".join(record.goal.split())
    if len(goal) > room:
        goal = goal[: room - 1].rstrip() + "…"
    return prefix + goal


def filter_records[R: AnyRecord](
    records: Iterable[R],
    *,
    status: RecordStatus | None = None,
    path_prefix: str | None = None,
    author_kind: AuthorKind | None = None,
) -> list[R]:
    """Keep records matching every given filter, newest first (ties broken by id, descending).

    ``path_prefix`` is a plain string prefix matched against every link path; a leading ``./``
    is ignored.
    """
    prefix = path_prefix.removeprefix("./") if path_prefix is not None else None
    kept = [
        r
        for r in records
        if (status is None or r.status == status)
        and (author_kind is None or r.author.kind == author_kind)
        and (prefix is None or any(link.path.startswith(prefix) for link in r.links))
    ]
    return sorted(kept, key=lambda r: (r.created_at, r.id), reverse=True)
