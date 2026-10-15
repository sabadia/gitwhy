"""Build and save draft records from what the author supplied.

Capture never invents a reason (CLAUDE.md invariant 1). Every narrative field is copied from
the input exactly; anything not supplied stays empty. Captured records are always drafts.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import uuid6
from pydantic import ValidationError

from whyline.config import load_config
from whyline.errors import UsageError
from whyline.gitio import staged_paths
from whyline.models import Record, SourceKind, utc_now
from whyline.store import WHYLINE_DIRNAME, RecordStore, describe_validation_error, write_pending


@dataclass(frozen=True)
class CaptureInput:
    """Everything an author supplied for one record. Flags, prompts, or a session map onto it.

    ``files`` are as the author typed them, relative to the working directory. When empty,
    capture links the staged files instead.
    """

    goal: str
    constraints: tuple[str, ...] = ()
    rejected: tuple[str, ...] = ()
    rejected_reasons: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    falsifier: str = ""
    risks: tuple[str, ...] = ()
    files: tuple[str, ...] = ()
    evidence_test: str | None = None
    adr: str | None = None
    author_name: str | None = None
    agent_tool: str | None = None
    source_kind: SourceKind = "flags"
    source_ref: str | None = None


@dataclass(frozen=True)
class CaptureResult:
    """The saved draft, where it was written, and whether it was marked pending."""

    record: Record
    path: Path
    pending: bool


def new_record_id() -> UUID:
    """Return a new time-ordered UUIDv7 as a plain ``uuid.UUID``."""
    return UUID(int=uuid6.uuid7().int)


def pair_rejected(options: Sequence[str], reasons: Sequence[str]) -> list[dict[str, str]]:
    """Pair each rejected option with the reason at the same position.

    A missing reason becomes ``""``. More reasons than options is a usage error.
    """
    if len(reasons) > len(options):
        raise UsageError(
            f"Got {len(reasons)} --rejected-reason values but only {len(options)} --rejected "
            "options.",
            hint="Pass one --rejected-reason per --rejected, in the same order.",
        )
    return [
        {"option": option, "reason": reasons[index] if index < len(reasons) else ""}
        for index, option in enumerate(options)
    ]


def resolve_files(files: Sequence[str], *, cwd: Path, root: Path) -> list[str]:
    """Turn paths typed relative to ``cwd`` into repo-relative POSIX paths, deduplicated in order.

    Paths are normalized lexically, so a file that no longer exists (for example, a deleted one)
    and a path through a symlinked directory keep the spelling the author used.
    """
    resolved: list[str] = []
    for raw in files:
        candidate = Path(raw)
        absolute = _lexical(candidate if candidate.is_absolute() else cwd / candidate)
        try:
            relative = absolute.relative_to(root)
        except ValueError:
            raise UsageError(
                f"{raw} is outside the repository ({root}).",
                hint="Pass paths to files inside the repository.",
            ) from None
        path = relative.as_posix()
        if path == ".":
            raise UsageError(
                f"{raw} is the repository root, not a file.",
                hint="Pass paths to files inside the repository.",
            )
        if path not in resolved:
            resolved.append(path)
    return resolved


def build_record(
    inp: CaptureInput, *, record_id: UUID, now: datetime, files: Sequence[str]
) -> Record:
    """Return a draft ``Record`` holding exactly what ``inp`` supplied, linked to ``files``.

    Input that breaks the schema (an empty goal, a goal over 500 characters, an unsafe path)
    raises ``UsageError``.
    """
    agent_tool = inp.agent_tool or None
    data: dict[str, Any] = {
        "schema_version": 1,
        "id": record_id,
        "status": "draft",
        "created_at": now,
        "updated_at": now,
        "affirmed_at": None,
        "affirmed_by": None,
        "author": {
            "kind": "agent" if agent_tool else "human",
            "name": inp.author_name,
            "tool": agent_tool,
        },
        "goal": inp.goal,
        "constraints": list(inp.constraints),
        "rejected": pair_rejected(inp.rejected, inp.rejected_reasons),
        "assumptions": list(inp.assumptions),
        "falsifier": inp.falsifier,
        "evidence": (
            [{"kind": "test", "ref": inp.evidence_test, "exit_code": None}]
            if inp.evidence_test is not None
            else []
        ),
        "links": [{"path": path, "start_line": None, "end_line": None} for path in files],
        "adr": inp.adr,
        "risks": list(inp.risks),
        "source": {"kind": inp.source_kind, "ref": inp.source_ref},
    }
    try:
        return Record.model_validate(data)
    except ValidationError as exc:
        raise UsageError(f"Cannot capture this record: {describe_validation_error(exc)}.") from exc


def capture(
    inp: CaptureInput,
    *,
    root: Path,
    cwd: Path,
    pending: bool = False,
    now: datetime | None = None,
    record_id: UUID | None = None,
) -> CaptureResult:
    """Build a draft from ``inp``, save it under ``root/.whyline``, and optionally mark it pending.

    Links are ``inp.files`` if given, else the staged files. The author name falls back to
    ``capture.default_author_name`` from config when not supplied.
    """
    store = RecordStore(root / WHYLINE_DIRNAME)
    store.require_initialized()
    files = resolve_files(inp.files, cwd=cwd, root=root) if inp.files else staged_paths(root)
    if not files:
        raise UsageError(
            "Nothing is staged and no --file was given, so the record would not point at any code.",
            hint="Stage your changes with `git add`, or pass --file PATH.",
        )
    if inp.author_name is None:
        inp = replace(inp, author_name=load_config(root).capture.default_author_name)
    record = build_record(
        inp,
        record_id=record_id if record_id is not None else new_record_id(),
        now=now if now is not None else utc_now(),
        files=files,
    )
    path = store.save(record)
    if pending:
        write_pending(store.whyline_dir, record.id)
    return CaptureResult(record=record, path=path, pending=pending)


def _lexical(path: Path) -> Path:
    """Collapse ``..`` in an absolute path without touching the filesystem."""
    parts: list[str] = []
    for part in path.parts[1:]:
        if part == "..":
            if parts:
                parts.pop()
        else:
            parts.append(part)
    return Path(path.anchor, *parts)
