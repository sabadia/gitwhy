"""Read and write records under ``.whyline/records`` with atomic replace."""

import os
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml
from pydantic import ValidationError

from whyline.errors import (
    CorruptError,
    NoRepoError,
    NotFoundError,
    SchemaVersionError,
    UsageError,
    WhylineError,
)
from whyline.models import SCHEMA_VERSION, Record, StoredRecord

WHYLINE_DIRNAME = ".whyline"
RECORDS_DIRNAME = "records"
RECORD_SUFFIX = ".yml"
SCHEMA_VERSION_FILENAME = "schema-version"

UPGRADE_HINT = "Upgrade whyline (for example `uv tool upgrade whyline`) and run the command again."

_YAML_WIDTH = 4096
"""Wide enough that a 500-character goal stays on one line, which keeps diffs readable."""


class _NoAliasDumper(yaml.SafeDumper):
    """Safe dumper that never emits anchors or aliases (docs/03 section 1)."""

    def ignore_aliases(self, data: Any) -> bool:
        return True


def dump_yaml(data: Mapping[str, Any]) -> str:
    """Serialize ``data`` as block-style YAML with keys in insertion order."""
    return yaml.dump(
        dict(data),
        Dumper=_NoAliasDumper,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=_YAML_WIDTH,
    )


def describe_validation_error(error: ValidationError, *, limit: int = 3) -> str:
    """Summarize a pydantic error as ``field: message`` pairs for a one-line user message."""
    parts = []
    for item in error.errors()[:limit]:
        message = str(item["msg"]).removeprefix("Value error, ")
        location = ".".join(str(part) for part in item["loc"])
        parts.append(f"{location}: {message}" if location else message)
    remaining = error.error_count() - limit
    if remaining > 0:
        parts.append(f"and {remaining} more")
    return "; ".join(parts)


def ensure_supported_schema(version: object, source: str) -> None:
    """Raise ``SchemaVersionError`` if ``version`` is newer than this whyline supports.

    Only integers are gated here. Any other value is left to model validation, which reports it
    as corrupt. A newer file is never guessed at: its fields may mean something this version
    does not know.
    """
    if isinstance(version, int) and not isinstance(version, bool) and version > SCHEMA_VERSION:
        raise SchemaVersionError(
            f"{source} uses schema version {version}, but this whyline supports only up to "
            f"version {SCHEMA_VERSION}.",
            hint=UPGRADE_HINT,
        )


def parse_record_id(record_id: UUID | str) -> UUID:
    """Return ``record_id`` as a UUID, rejecting anything that is not one."""
    if isinstance(record_id, UUID):
        return record_id
    try:
        return UUID(record_id)
    except ValueError:
        raise UsageError(
            f"{record_id!r} is not a record id (expected a UUID such as "
            "01932a7e-5b1c-7c3a-8f21-9c0e4d2a1b77).",
            hint="Run `whyline list` to see record ids.",
        ) from None


@dataclass(frozen=True)
class ListResult:
    """Records that loaded, plus one error per file that did not."""

    records: list[StoredRecord] = field(default_factory=list)
    errors: list[WhylineError] = field(default_factory=list)


class RecordStore:
    """Records stored as one YAML file per id in ``<whyline_dir>/records``."""

    def __init__(self, whyline_dir: Path) -> None:
        self.whyline_dir = whyline_dir

    @property
    def records_dir(self) -> Path:
        """Directory holding the record files."""
        return self.whyline_dir / RECORDS_DIRNAME

    def path_for(self, record_id: UUID | str) -> Path:
        """Return the file path for ``record_id``. The id is validated first."""
        return self.records_dir / f"{parse_record_id(record_id)}{RECORD_SUFFIX}"

    def save(self, record: Record | StoredRecord) -> Path:
        """Validate ``record`` and write it atomically. Returns the file path.

        The file is written to a temporary name in the same directory, flushed to disk, and
        renamed over the target, so a crash never leaves a half-written record.
        """
        self._require_records_dir()
        try:
            validated = type(record).model_validate(record.model_dump())
        except ValidationError as exc:
            raise CorruptError(
                f"Refusing to save record {record.id}: {describe_validation_error(exc)}."
            ) from exc
        target = self.path_for(validated.id)
        _atomic_write(target, dump_yaml(validated.model_dump(mode="json")))
        return target

    def load(self, record_id: UUID | str) -> StoredRecord:
        """Load one record by id."""
        self._require_records_dir()
        path = self.path_for(record_id)
        if not path.is_file():
            raise NotFoundError(
                f"No record with id {parse_record_id(record_id)} ({self._display(path)}).",
                hint="Run `whyline list` to see record ids.",
            )
        return self.load_path(path)

    def load_path(self, path: Path) -> StoredRecord:
        """Load and validate the record file at ``path``."""
        shown = self._display(path)
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise NotFoundError(f"Record file {shown} does not exist.") from None
        except UnicodeDecodeError:
            raise CorruptError(f"Record file {shown} is not UTF-8 text.", hint=_FIX_HINT) from None
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            problem = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
            raise CorruptError(
                f"Record file {shown} is not valid YAML ({problem}).", hint=_FIX_HINT
            ) from exc
        if not isinstance(data, dict):
            raise CorruptError(f"Record file {shown} is not a YAML mapping.", hint=_FIX_HINT)
        ensure_supported_schema(data.get("schema_version"), f"Record file {shown}")
        try:
            record = StoredRecord.model_validate(data)
        except ValidationError as exc:
            raise CorruptError(
                f"Record {path.stem} failed validation ({shown}): "
                f"{describe_validation_error(exc)}.",
                hint=_FIX_HINT,
            ) from exc
        if path.name != f"{record.id}{RECORD_SUFFIX}":
            raise CorruptError(
                f"Record file {shown} contains id {record.id}, which does not match its file name.",
                hint=f"Rename the file to {record.id}{RECORD_SUFFIX}.",
            )
        return record

    def _require_records_dir(self) -> None:
        if not self.records_dir.is_dir():
            raise NoRepoError(
                f"Whyline is not initialized here ({self._display(self.records_dir)} is missing).",
                hint="Run `whyline init`.",
            )
        self._check_repo_schema_version()

    def _check_repo_schema_version(self) -> None:
        """Gate on ``.whyline/schema-version``. A missing file is treated as version 1."""
        path = self.whyline_dir / SCHEMA_VERSION_FILENAME
        try:
            text = path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return
        except (OSError, UnicodeDecodeError) as exc:
            raise CorruptError(
                f"Cannot read {self._display(path)}: {exc}.", hint="Run `whyline init --force`."
            ) from exc
        try:
            version = int(text)
        except ValueError:
            raise CorruptError(
                f"{self._display(path)} should contain a schema version number, got {text!r}.",
                hint="Run `whyline init --force`.",
            ) from None
        ensure_supported_schema(version, f"This repository ({self._display(path)})")

    def _display(self, path: Path) -> str:
        try:
            return path.relative_to(self.whyline_dir.parent).as_posix()
        except ValueError:
            return str(path)

    def list(self) -> ListResult:
        """Load every record file. Files that fail are reported in ``errors``, not raised."""
        self._require_records_dir()
        result = ListResult()
        for path in sorted(self.records_dir.glob(f"*{RECORD_SUFFIX}")):
            if path.name.startswith("."):
                continue
            try:
                result.records.append(self.load_path(path))
            except WhylineError as exc:
                result.errors.append(exc)
        return result


_FIX_HINT = "Fix the file or run `whyline capture` again."


def _atomic_write(target: Path, text: str) -> None:
    tmp = target.with_name(f".{target.name}.{secrets.token_hex(6)}.tmp")
    # os.open with 0o666 lets the umask decide permissions, like a normal file write.
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        tmp.replace(target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    _fsync_directory(target.parent)


def _fsync_directory(directory: Path) -> None:
    """Persist the rename on POSIX. Windows cannot open directories, so skip it there."""
    if os.name != "posix":  # pragma: no cover - CI runs on Linux
        return
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
