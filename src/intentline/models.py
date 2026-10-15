"""Pydantic models for intentline records and config (docs/03 sections 1, 2 and 9).

Read/write split (docs/03 section 9): every record shape exists twice.

- The *writer* models (``Record`` and its parts) use ``extra="forbid"``. Records this version
  creates contain only fields it knows.
- The *reader* models (``StoredRecord`` and its parts) use ``extra="allow"``. A file written
  by a newer intentline that added optional fields still loads, and the unknown keys survive a
  load/save round-trip instead of being dropped.

Both families share one field list through generic bases, so they cannot drift apart.
"""

import json
from datetime import UTC, datetime
from pathlib import PurePosixPath, PureWindowsPath
from typing import Annotated, Any, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from pydantic.types import UUID7

SCHEMA_VERSION = 1
"""Record and config schema version this release reads and writes."""

RecordStatus = Literal["draft", "affirmed"]
AuthorKind = Literal["human", "agent"]
EvidenceKind = Literal["test", "command", "note"]
SourceKind = Literal["prompt", "flags", "session", "import"]

UtcDatetime = Annotated[AwareDatetime, Field(description="RFC3339 timestamp, stored in UTC")]


def _reject_bool(value: object) -> object:
    # Literal[1] would otherwise accept True, because True == 1 in Python.
    if isinstance(value, bool):
        raise ValueError("schema_version must be an integer")
    return value


SchemaVersion = Annotated[Literal[1], BeforeValidator(_reject_bool)]

_WRITE = ConfigDict(extra="forbid")
_READ = ConfigDict(extra="allow")


def utc_now() -> datetime:
    """Return the current time in UTC, truncated to whole seconds (stored as ``…Z``)."""
    return datetime.now(UTC).replace(microsecond=0)


def _to_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


def _check_relative_path(value: str) -> str:
    """Reject paths that could escape the repository: absolute, drive-rooted, or with ``..``."""
    if not value:
        raise ValueError("path must not be empty")
    windows = PureWindowsPath(value)
    if PurePosixPath(value).is_absolute() or windows.is_absolute() or windows.drive:
        raise ValueError(f"path must be relative to the repository root, got {value!r}")
    if ".." in windows.parts:
        raise ValueError(f"path must not contain '..', got {value!r}")
    return value


# --- record parts -----------------------------------------------------------------------------


class _AuthorBase(BaseModel):
    kind: AuthorKind
    name: str | None = None
    tool: str | None = None

    @model_validator(mode="after")
    def _tool_matches_kind(self) -> Self:
        if self.kind == "agent" and not self.tool:
            raise ValueError("author.tool is required when author.kind is agent")
        if self.kind == "human" and self.tool is not None:
            raise ValueError("author.tool must be null when author.kind is human")
        return self


class _RejectedBase(BaseModel):
    option: str = Field(min_length=1, max_length=300)
    reason: str = ""


class _EvidenceBase(BaseModel):
    kind: EvidenceKind
    ref: str = Field(min_length=1)
    exit_code: int | None = None


class _LinkBase(BaseModel):
    path: str
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)

    @field_validator("path")
    @classmethod
    def _relative_path(cls, value: str) -> str:
        return _check_relative_path(value)

    @model_validator(mode="after")
    def _ordered_lines(self) -> Self:
        if (
            self.start_line is not None
            and self.end_line is not None
            and self.start_line > self.end_line
        ):
            raise ValueError(
                f"start_line {self.start_line} is greater than end_line {self.end_line}"
            )
        return self


class _SourceBase(BaseModel):
    kind: SourceKind
    ref: str | None = None


class Author(_AuthorBase):
    """Who wrote a record. Agents must name their tool; humans must not."""

    model_config = _WRITE


class Rejected(_RejectedBase):
    """An alternative that was considered and rejected."""

    model_config = _WRITE


class Evidence(_EvidenceBase):
    """A test, command, or note offered as evidence. Stored, never re-run."""

    model_config = _WRITE


class Link(_LinkBase):
    """A repository-relative path, optionally narrowed to a line range."""

    model_config = _WRITE


class Source(_SourceBase):
    """How the record was captured."""

    model_config = _WRITE


class StoredAuthor(_AuthorBase):
    """Reader variant of ``Author`` that keeps unknown keys."""

    model_config = _READ


class StoredRejected(_RejectedBase):
    """Reader variant of ``Rejected`` that keeps unknown keys."""

    model_config = _READ


class StoredEvidence(_EvidenceBase):
    """Reader variant of ``Evidence`` that keeps unknown keys."""

    model_config = _READ


class StoredLink(_LinkBase):
    """Reader variant of ``Link`` that keeps unknown keys."""

    model_config = _READ


class StoredSource(_SourceBase):
    """Reader variant of ``Source`` that keeps unknown keys."""

    model_config = _READ


# --- record -----------------------------------------------------------------------------------


class _RecordBase[
    AuthorT: _AuthorBase,
    RejectedT: _RejectedBase,
    EvidenceT: _EvidenceBase,
    LinkT: _LinkBase,
    SourceT: _SourceBase,
](BaseModel):
    """Fields of a record, in the order of docs/03 section 1."""

    schema_version: SchemaVersion
    id: UUID7
    status: RecordStatus
    created_at: UtcDatetime
    updated_at: UtcDatetime
    affirmed_at: UtcDatetime | None
    affirmed_by: str | None
    author: AuthorT
    goal: str = Field(min_length=1, max_length=500)
    constraints: list[str]
    rejected: list[RejectedT]
    assumptions: list[str]
    falsifier: str
    evidence: list[EvidenceT]
    links: list[LinkT] = Field(min_length=1)
    adr: str | None = None
    risks: list[str]
    source: SourceT

    @field_validator("created_at", "updated_at", "affirmed_at")
    @classmethod
    def _normalize_utc(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _to_utc(value)

    @model_validator(mode="after")
    def _affirmation_matches_status(self) -> Self:
        if self.status == "affirmed":
            if self.affirmed_at is None:
                raise ValueError("affirmed_at is null while status is affirmed")
            if not self.affirmed_by:
                raise ValueError("affirmed_by is empty while status is affirmed")
        else:
            if self.affirmed_at is not None:
                raise ValueError("affirmed_at is set while status is draft")
            if self.affirmed_by is not None:
                raise ValueError("affirmed_by is set while status is draft")
        return self


class Record(_RecordBase[Author, Rejected, Evidence, Link, Source]):
    """A record as this version writes it. Unknown keys are rejected."""

    model_config = _WRITE


class StoredRecord(
    _RecordBase[StoredAuthor, StoredRejected, StoredEvidence, StoredLink, StoredSource]
):
    """A record as read from disk. Unknown keys are kept so a save does not drop them."""

    model_config = _READ


JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"


def record_json_schema() -> dict[str, Any]:
    """Return the JSON Schema for a record, generated from the writer model ``Record``.

    This is the compatibility surface for other tools (docs/02 section 8). The committed copy
    in ``schema/record.schema.json`` must match this output; a test enforces it.
    """
    schema = Record.model_json_schema()
    schema["description"] = f"A Intentline intent record, schema version {SCHEMA_VERSION}."
    return {"$schema": JSON_SCHEMA_DIALECT, **schema}


def render_record_json_schema() -> str:
    """Return ``record_json_schema()`` as stable, pretty-printed JSON ending in a newline."""
    return json.dumps(record_json_schema(), indent=2, ensure_ascii=False) + "\n"


# --- config -----------------------------------------------------------------------------------

DEFAULT_CHECK_IGNORE: tuple[str, ...] = (
    "uv.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    "*.lock",
    ".intentline/**",
    "schema/**",
    "*generated*",
)


class CheckConfig(BaseModel):
    """Settings for ``intentline check``."""

    model_config = _WRITE

    enabled: bool = False
    min_lines: int = Field(default=30, ge=0)
    ignore: list[str] = Field(default_factory=lambda: list(DEFAULT_CHECK_IGNORE))


class HooksConfig(BaseModel):
    """Which git hooks intentline manages."""

    model_config = _WRITE

    trailer: bool = True
    check: bool = False


class CaptureConfig(BaseModel):
    """Defaults for ``intentline capture``."""

    model_config = _WRITE

    default_author_name: str | None = None


class Config(BaseModel):
    """Project or user config (``.intentline/config.yml``). Every key has a default.

    Config is hand-edited, so unknown keys are rejected to catch typos.
    """

    model_config = _WRITE

    schema_version: SchemaVersion = 1
    check: CheckConfig = Field(default_factory=CheckConfig)
    hooks: HooksConfig = Field(default_factory=HooksConfig)
    capture: CaptureConfig = Field(default_factory=CaptureConfig)
