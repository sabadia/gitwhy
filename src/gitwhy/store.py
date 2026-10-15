"""Read and write records under ``.gitwhy/records`` with atomic replace."""

import os
import secrets
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml
from pydantic import ValidationError

from gitwhy.errors import (
    CorruptError,
    GitwhyError,
    NoRepoError,
    NotFoundError,
    SchemaVersionError,
    UsageError,
)
from gitwhy.models import SCHEMA_VERSION, Config, Record, StoredRecord

GITWHY_DIRNAME = ".gitwhy"
RECORDS_DIRNAME = "records"
RECORD_SUFFIX = ".yml"
SCHEMA_VERSION_FILENAME = "schema-version"
CONFIG_FILENAME = "config.yml"
GITIGNORE_FILENAME = ".gitignore"
PENDING_FILENAME = "pending"
GITKEEP_FILENAME = ".gitkeep"

UPGRADE_HINT = "Upgrade gitwhy (for example `uv tool upgrade gitwhy`) and run the command again."

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
    """Raise ``SchemaVersionError`` if ``version`` is newer than this gitwhy supports.

    Only integers are gated here. Any other value is left to model validation, which reports it
    as corrupt. A newer file is never guessed at: its fields may mean something this version
    does not know.
    """
    if isinstance(version, int) and not isinstance(version, bool) and version > SCHEMA_VERSION:
        raise SchemaVersionError(
            f"{source} uses schema version {version}, but this gitwhy supports only up to "
            f"version {SCHEMA_VERSION}.",
            hint=UPGRADE_HINT,
        )


def read_repo_schema_version(gitwhy_dir: Path) -> int | None:
    """Return the number in ``.gitwhy/schema-version``, or None if the file does not exist.

    Raises ``CorruptError`` if the file cannot be read or does not hold an integer.
    """
    path = gitwhy_dir / SCHEMA_VERSION_FILENAME
    shown = _display(path, gitwhy_dir.parent)
    try:
        text = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as exc:
        raise CorruptError(
            f"Cannot read {shown}: {exc}.", hint="Run `gitwhy init --force`."
        ) from exc
    try:
        return int(text)
    except ValueError:
        raise CorruptError(
            f"{shown} should contain a schema version number, got {text!r}.",
            hint="Run `gitwhy init --force`.",
        ) from None


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
            hint="Run `gitwhy list` to see record ids.",
        ) from None


@dataclass(frozen=True)
class ListResult:
    """Records that loaded, plus one error per file that did not."""

    records: list[StoredRecord] = field(default_factory=list)
    errors: list[GitwhyError] = field(default_factory=list)


class RecordStore:
    """Records stored as one YAML file per id in ``<gitwhy_dir>/records``."""

    def __init__(self, gitwhy_dir: Path) -> None:
        self.gitwhy_dir = gitwhy_dir

    @property
    def records_dir(self) -> Path:
        """Directory holding the record files."""
        return self.gitwhy_dir / RECORDS_DIRNAME

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
                hint="Run `gitwhy list` to see record ids.",
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

    def require_initialized(self) -> None:
        """Raise ``NoRepoError`` (or a schema error) unless this store is ready to use."""
        self._require_records_dir()

    def _require_records_dir(self) -> None:
        if not self.records_dir.is_dir():
            raise NoRepoError(
                f"Gitwhy is not initialized here ({self._display(self.records_dir)} is missing).",
                hint="Run `gitwhy init`.",
            )
        self._check_repo_schema_version()

    def _check_repo_schema_version(self) -> None:
        """Gate on ``.gitwhy/schema-version``. A missing file is treated as version 1."""
        version = read_repo_schema_version(self.gitwhy_dir)
        if version is not None:
            path = self.gitwhy_dir / SCHEMA_VERSION_FILENAME
            ensure_supported_schema(version, f"This repository ({self._display(path)})")

    def _display(self, path: Path) -> str:
        return _display(path, self.gitwhy_dir.parent)

    def list(self) -> ListResult:
        """Load every record file. Files that fail are reported in ``errors``, not raised."""
        return self._load_files(self._iter_record_files())

    def mentioning(self, needle: str) -> ListResult:
        """Load record files whose text contains ``needle``.

        A file that does not contain ``needle`` cannot link that path, so it is not
        parsed. A mention in the goal is not itself a link: callers check the links.
        A file that cannot be read as text is loaded anyway, so a corrupt file still
        shows up in ``errors``.
        """
        paths: list[Path] = []
        for path in self._iter_record_files():
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                paths.append(path)
                continue
            if needle in text:
                paths.append(path)
        return self._load_files(paths)

    def _iter_record_files(self) -> Iterator[Path]:
        self._require_records_dir()
        for path in sorted(self.records_dir.glob(f"*{RECORD_SUFFIX}")):
            if not path.name.startswith("."):
                yield path

    def _load_files(self, paths: Iterable[Path]) -> ListResult:
        result = ListResult()
        for path in paths:
            try:
                result.records.append(self.load_path(path))
            except GitwhyError as exc:
                result.errors.append(exc)
        return result


_FIX_HINT = "Fix the file or run `gitwhy capture` again."


def _display(path: Path, base: Path) -> str:
    """Show ``path`` relative to ``base`` (the repository root) when it is inside it."""
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return str(path)


# --- gitwhy init -------------------------------------------------------------------------

CONFIG_HEADER = (
    "# Gitwhy project config. The commented keys below show the built-in defaults.\n"
    "# Uncomment a key to set it for everyone using this repository; a project value\n"
    "# overrides the same key in each user's ~/.config/gitwhy/config.yml.\n"
)


@dataclass(frozen=True)
class InitResult:
    """What ``initialize`` did to each managed path."""

    gitwhy_dir: Path
    created: list[Path] = field(default_factory=list)
    updated: list[Path] = field(default_factory=list)
    unchanged: list[Path] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        """True if any file or directory was created or rewritten."""
        return bool(self.created or self.updated)


def default_config_text() -> str:
    """Return the YAML written to a new ``.gitwhy/config.yml``.

    Only ``schema_version`` is set. Writing the defaults as live values would make the project
    layer override every key of the user config (docs/02 section 5), so they are written as
    comments generated from ``Config`` and cannot drift from the model.
    """
    defaults = Config().model_dump(mode="json")
    version = defaults.pop("schema_version")
    commented = "".join(f"# {line}\n" for line in dump_yaml(defaults).splitlines())
    return f"{CONFIG_HEADER}schema_version: {version}\n\n{commented}"


def initialize(repo_root: Path, *, force: bool = False) -> InitResult:
    """Create the ``.gitwhy`` layout in ``repo_root``. Safe to run again.

    Creates whatever is missing: ``config.yml``, ``schema-version``, ``records/.gitkeep``, and a
    ``.gitignore`` that lists ``pending``. An existing config is left alone unless ``force`` is
    set, in which case it is reset to defaults. Records are never modified or deleted. A
    repository marked with a newer schema version is refused, even with ``force``.
    """
    gitwhy_dir = repo_root / GITWHY_DIRNAME
    if gitwhy_dir.exists() and not gitwhy_dir.is_dir():
        raise CorruptError(
            f"{_display(gitwhy_dir, repo_root)} exists but is not a directory.",
            hint="Move it aside and run `gitwhy init` again.",
        )
    result = InitResult(gitwhy_dir=gitwhy_dir)

    version_path = gitwhy_dir / SCHEMA_VERSION_FILENAME
    try:
        version = read_repo_schema_version(gitwhy_dir)
    except CorruptError:
        if not force:
            raise
        version = -1  # unreadable; rewritten below
    if version is not None:
        ensure_supported_schema(version, f"This repository ({_display(version_path, repo_root)})")

    records_dir = gitwhy_dir / RECORDS_DIRNAME
    if records_dir.is_dir():
        result.unchanged.append(records_dir)
    else:
        records_dir.mkdir(parents=True)
        result.created.append(records_dir)

    _ensure_file(result, records_dir / GITKEEP_FILENAME, "")

    if version is None:
        _atomic_write(version_path, f"{SCHEMA_VERSION}\n")
        result.created.append(version_path)
    elif version != SCHEMA_VERSION:
        _atomic_write(version_path, f"{SCHEMA_VERSION}\n")
        result.updated.append(version_path)
    else:
        result.unchanged.append(version_path)

    config_path = gitwhy_dir / CONFIG_FILENAME
    if not config_path.exists():
        _atomic_write(config_path, default_config_text())
        result.created.append(config_path)
    elif force:
        _atomic_write(config_path, default_config_text())
        result.updated.append(config_path)
    else:
        result.unchanged.append(config_path)

    _ensure_gitignore_lists_pending(result, gitwhy_dir / GITIGNORE_FILENAME)
    return result


def write_pending(gitwhy_dir: Path, record_id: UUID) -> Path:
    """Write ``record_id`` (only the id, plus a newline) to ``.gitwhy/pending``.

    The prepare-commit-msg hook reads this file to add the ``Gitwhy-Id`` trailer. It is local
    state: ``gitwhy init`` lists ``pending`` in ``.gitwhy/.gitignore``.
    """
    path = gitwhy_dir / PENDING_FILENAME
    _atomic_write(path, f"{record_id}\n")
    return path


def read_pending(gitwhy_dir: Path) -> UUID | None:
    """Return the id in ``.gitwhy/pending``, or None if it is missing, empty, or not a UUID."""
    try:
        text = (gitwhy_dir / PENDING_FILENAME).read_text(encoding="utf-8").strip()
    except (FileNotFoundError, UnicodeDecodeError):
        return None
    try:
        return UUID(text)
    except ValueError:
        return None


def _ensure_file(result: InitResult, path: Path, text: str) -> None:
    if path.exists():
        result.unchanged.append(path)
    else:
        _atomic_write(path, text)
        result.created.append(path)


def _ensure_gitignore_lists_pending(result: InitResult, path: Path) -> None:
    """Make sure ``.gitwhy/.gitignore`` ignores ``pending``, keeping any other lines."""
    try:
        current = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        _atomic_write(path, f"{PENDING_FILENAME}\n")
        result.created.append(path)
        return
    if PENDING_FILENAME in (line.strip() for line in current.splitlines()):
        result.unchanged.append(path)
        return
    separator = "" if current == "" or current.endswith("\n") else "\n"
    _atomic_write(path, f"{current}{separator}{PENDING_FILENAME}\n")
    result.updated.append(path)


def atomic_write_text(target: Path, text: str) -> None:
    """Write ``text`` to ``target`` atomically (temp file in the same directory, then rename)."""
    _atomic_write(target, text)


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
