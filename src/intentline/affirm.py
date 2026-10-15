"""Affirm a draft record: the human gate (docs/03 section 4, docs/05 section 5).

Agents may draft records; only a human may affirm one. The gate is a terminal check: affirming
from a non-interactive shell is refused unless the caller passes ``--i-am-human``. Callers
inject everything that touches the outside world (terminal state, the confirmation prompt,
the clock), so the rules stay testable and reusable by ``capture --affirm``.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from uuid import UUID

from intentline.errors import AffirmRefusedError, UsageError
from intentline.gitio import config_value
from intentline.models import Record, StoredRecord
from intentline.store import RecordStore

EMPTY_FIELD_NAMES: tuple[str, ...] = (
    "constraints",
    "rejected",
    "assumptions",
    "falsifier",
    "evidence",
    "risks",
)
"""Optional narrative fields. Empty is valid on a draft and only a warning on affirm."""


@dataclass(frozen=True)
class AffirmOutcome:
    """Result of ``affirm_record``."""

    record: StoredRecord
    already_affirmed: bool = False
    empty_fields: list[str] = field(default_factory=list)


def require_human(*, interactive: bool, i_am_human: bool) -> None:
    """Refuse unless a human is at an interactive terminal or explicitly vouched for it."""
    if interactive or i_am_human:
        return
    raise AffirmRefusedError(
        "Refusing to affirm from a non-interactive shell: affirming a record is a human "
        "decision, and agents may only draft.",
        hint="Run `intentline affirm` yourself in a terminal. If you are a human on a "
        "non-interactive shell, pass --i-am-human (you are lying if you are not).",
    )


def empty_narrative_fields(record: Record | StoredRecord) -> list[str]:
    """Return the optional narrative fields that are empty, in ``EMPTY_FIELD_NAMES`` order."""
    return [name for name in EMPTY_FIELD_NAMES if not getattr(record, name)]


def apply_affirmation[R: (Record, StoredRecord)](record: R, *, by: str, now: datetime) -> R:
    """Return a validated copy of ``record`` marked affirmed by ``by`` at ``now``.

    Only status and affirmation timestamps change. Narrative fields are never filled in.
    """
    data = record.model_dump()
    data.update(status="affirmed", affirmed_at=now, affirmed_by=by, updated_at=now)
    return type(record).model_validate(data)


def resolve_affirmer(by: str | None, repo_root: Path) -> str:
    """Return who is affirming: ``--by``, else git ``user.name``, else raise ``UsageError``."""
    for candidate in (by, config_value("user.name", repo_root)):
        if candidate is not None and candidate.strip():
            return candidate.strip()
    raise UsageError(
        "Cannot tell who is affirming: no --by was given and git user.name is not set.",
        hint='Pass --by "Your Name".',
    )


def affirm_record(
    store: RecordStore,
    record_id: UUID | str,
    *,
    by: str,
    interactive: bool,
    i_am_human: bool,
    yes: bool,
    confirm: Callable[[list[str]], bool],
    now: datetime,
) -> AffirmOutcome:
    """Affirm the record ``record_id`` after the human gate. See the module docstring.

    The gate runs before the record is loaded. An already affirmed record is left unchanged.
    Empty narrative fields need confirmation on an interactive terminal unless ``yes``; on the
    ``--i-am-human`` path they are returned for the caller to show as a warning.
    """
    require_human(interactive=interactive, i_am_human=i_am_human)
    record = store.load(record_id)
    if record.status == "affirmed":
        return AffirmOutcome(record=record, already_affirmed=True)
    empty = empty_narrative_fields(record)
    if empty and interactive and not yes and not confirm(empty):
        raise UsageError(f"Not affirmed. Record {record.id} is unchanged.")
    affirmed = apply_affirmation(record, by=by, now=now)
    store.save(affirmed)
    return AffirmOutcome(record=affirmed, empty_fields=empty)
