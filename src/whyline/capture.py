"""Build and save draft records from what the author supplied.

Capture never invents a reason (CLAUDE.md invariant 1). Every narrative field is copied from
the input exactly; anything not supplied stays empty. Captured records are always drafts.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import uuid6
from pydantic import ValidationError

from whyline.affirm import apply_affirmation, empty_narrative_fields, require_human
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


GOAL_QUESTION = "What is this change for?"
REJECTED_QUESTION = "What did you consider and reject? (optional, press Enter to skip)"
FALSIFIER_QUESTION = "What would prove this wrong? (optional, press Enter to skip)"

Ask = Callable[[str, bool], str]
"""Ask one question and return the answer. The bool says whether an answer is required."""


def prompt_missing(inp: CaptureInput, ask: Ask) -> CaptureInput:
    """Ask the three capture questions (docs/03 section 4) for fields that are still missing.

    1. The goal, if empty. Required: asked again until the answer is not blank.
    2. A rejected alternative, unless ``--rejected`` supplied one. Optional.
    3. A falsifier, unless one was supplied. Optional.

    Answers are stored exactly as typed. A blank optional answer leaves the field empty, and
    nothing else is asked. If any question was asked, ``source_kind`` becomes ``"prompt"``.
    """
    changes: dict[str, Any] = {}
    asked = False
    if not inp.goal.strip():
        answer = ""
        while not answer.strip():
            answer = ask(GOAL_QUESTION, True)
        changes["goal"] = answer
        asked = True
    if not inp.rejected:
        answer = ask(REJECTED_QUESTION, False)
        asked = True
        if answer.strip():
            changes["rejected"] = (answer,)
    if not inp.falsifier.strip():
        answer = ask(FALSIFIER_QUESTION, False)
        asked = True
        if answer.strip():
            changes["falsifier"] = answer
    if asked:
        changes["source_kind"] = "prompt"
    return replace(inp, **changes)


@dataclass(frozen=True)
class AffirmRequest:
    """Affirm the record in the same step it is captured (``capture --affirm``).

    The human gate and the empty-field confirmation are the same as ``whyline affirm``.
    """

    by: str
    interactive: bool
    i_am_human: bool
    yes: bool
    confirm: Callable[[list[str]], bool]


@dataclass(frozen=True)
class CaptureResult:
    """The saved record, where it was written, and whether it was marked pending.

    ``empty_fields`` lists empty narrative fields of a record affirmed at capture time.
    """

    record: Record
    path: Path
    pending: bool
    empty_fields: tuple[str, ...] = ()


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


def linked_files(inp: CaptureInput, *, root: Path, cwd: Path) -> list[str]:
    """Check that capture can run, and return the paths the record will link.

    Raises before anything is written: not initialized (exit 2), a path outside the repository,
    or nothing staged and no files given (exit 1). Interactive capture calls this before asking
    any question, so nobody answers three questions only to be told nothing is staged.
    """
    RecordStore(root / WHYLINE_DIRNAME).require_initialized()
    files = resolve_files(inp.files, cwd=cwd, root=root) if inp.files else staged_paths(root)
    if not files:
        raise UsageError(
            "Nothing is staged and no --file was given, so the record would not point at any code.",
            hint="Stage your changes with `git add`, or pass --file PATH.",
        )
    return files


def capture(
    inp: CaptureInput,
    *,
    root: Path,
    cwd: Path,
    pending: bool = False,
    now: datetime | None = None,
    record_id: UUID | None = None,
    affirm: AffirmRequest | None = None,
) -> CaptureResult:
    """Build a draft from ``inp``, save it under ``root/.whyline``, and optionally mark it pending.

    Links are ``inp.files`` if given, else the staged files. The author name falls back to
    ``capture.default_author_name`` from config when not supplied.

    With ``affirm``, the human gate runs before anything else, and the record is affirmed
    before its single save. A refused gate or a declined confirmation writes nothing.
    """
    if affirm is not None:
        require_human(interactive=affirm.interactive, i_am_human=affirm.i_am_human)
    store = RecordStore(root / WHYLINE_DIRNAME)
    files = linked_files(inp, root=root, cwd=cwd)
    if inp.author_name is None:
        inp = replace(inp, author_name=load_config(root).capture.default_author_name)
    record = build_record(
        inp,
        record_id=record_id if record_id is not None else new_record_id(),
        now=now if now is not None else utc_now(),
        files=files,
    )
    empty: list[str] = []
    if affirm is not None:
        empty = empty_narrative_fields(record)
        if empty and affirm.interactive and not affirm.yes and not affirm.confirm(empty):
            raise UsageError("Not captured: you declined to affirm with empty fields.")
        record = apply_affirmation(record, by=affirm.by, now=record.created_at)
    path = store.save(record)
    if pending:
        write_pending(store.whyline_dir, record.id)
    return CaptureResult(record=record, path=path, pending=pending, empty_fields=tuple(empty))


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
