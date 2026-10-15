"""Read a goal candidate and touched files from a session log, without inventing anything.

A session log is an input to capture, never a stored artifact (docs/01 section 7). Only two
facts are taken from it: the first user message (as the goal candidate) and a top-level
``files`` list when one is present. Prose that looks like a rejected alternative, an
assumption, or a falsifier is deliberately ignored: those fields stay empty unless a human
types them (CLAUDE.md invariant 1).
"""

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from whyline.errors import NotFoundError, UsageError

GOAL_MAX_LENGTH = 500
_ELLIPSIS = "…"


@dataclass(frozen=True)
class SessionFacts:
    """What a session log literally contains that capture may use."""

    goal: str | None
    files: tuple[str, ...] = ()


def read_session(path: Path) -> SessionFacts:
    """Read ``path`` and return its goal candidate and listed files.

    A missing file raises ``NotFoundError`` (exit 9). A file that cannot be read as UTF-8 text
    raises ``UsageError`` (exit 1).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise NotFoundError(
            f"Session file {path} does not exist.", hint="Pass the path of a session log."
        ) from None
    except UnicodeDecodeError:
        raise UsageError(
            f"Session file {path} is not UTF-8 text.",
            hint="Pass a text or JSON session log, or use --goal.",
        ) from None
    except OSError as exc:
        raise UsageError(
            f"Cannot read session file {path}: {exc.strerror or exc}.",
            hint="Pass a readable text or JSON session log.",
        ) from None
    return parse_session(text)


def parse_session(text: str) -> SessionFacts:
    """Return the facts in a session log's text.

    Shapes, in order: a JSON object with a ``messages`` list; a JSON array of messages; JSONL
    with one JSON object per line; otherwise plain text, whose first non-empty line is the goal.
    Valid JSON of any other shape yields no goal rather than a guess.
    """
    stripped = text.strip()
    is_json = False
    data: Any = None
    if stripped:
        try:
            data = json.loads(stripped)
            is_json = True
        except json.JSONDecodeError:
            pass
    if isinstance(data, Mapping) and isinstance(data.get("messages"), list):
        return SessionFacts(goal=_first_user_text(data["messages"]), files=_files(data))
    if isinstance(data, list):
        return SessionFacts(goal=_first_user_text(data))
    lines = _jsonl_objects(stripped)
    if lines is not None:
        files = next((found for line in lines if (found := _files(line))), ())
        return SessionFacts(goal=_first_user_text(lines), files=files)
    if is_json:
        return SessionFacts(goal=None)
    first_line = next((line for line in stripped.splitlines() if line.strip()), None)
    return SessionFacts(goal=None if first_line is None else _goal(first_line))


def session_source_ref(path: Path, root: Path) -> str:
    """Return how a record names its session: repo-relative if inside ``root``, else the name.

    Records are committed, so a session outside the repository is named by its file name only,
    never by an absolute path that could expose a home directory.
    """
    absolute = path.absolute()
    try:
        return absolute.relative_to(root).as_posix()
    except ValueError:
        return absolute.name


def session_files_in_repo(files: Iterable[str], root: Path) -> tuple[str, ...]:
    """Return the session's listed files that lie inside ``root``, as absolute paths.

    Relative entries are taken relative to the repository root. Entries outside the repository
    are dropped, since a record can only link files in the repository.
    """
    kept: list[str] = []
    for entry in files:
        candidate = Path(entry)
        absolute = candidate if candidate.is_absolute() else root / candidate
        try:
            relative = absolute.relative_to(root)
        except ValueError:
            continue
        if ".." in relative.parts or relative == Path():
            continue
        kept.append(str(absolute))
    return tuple(kept)


def _goal(text: str) -> str | None:
    collapsed = " ".join(text.split())
    if not collapsed:
        return None
    if len(collapsed) > GOAL_MAX_LENGTH:
        return collapsed[: GOAL_MAX_LENGTH - 1] + _ELLIPSIS
    return collapsed


def _first_user_text(messages: Iterable[Any]) -> str | None:
    for message in messages:
        goal = _goal(_user_text(message) or "")
        if goal is not None:
            return goal
    return None


def _user_text(message: Any) -> str | None:
    if not isinstance(message, Mapping):
        return None
    if message.get("role") == "user":
        return _content_text(message.get("content"))
    inner = message.get("message")
    if message.get("type") == "user" and isinstance(inner, Mapping) and inner.get("role") == "user":
        return _content_text(inner.get("content"))
    return None


def _content_text(content: Any) -> str | None:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            part["text"]
            for part in content
            if isinstance(part, Mapping)
            and part.get("type") == "text"
            and isinstance(part.get("text"), str)
        ]
        return "\n".join(parts) if parts else None
    return None


def _files(container: Mapping[str, Any]) -> tuple[str, ...]:
    files = container.get("files")
    if not isinstance(files, list):
        return ()
    return tuple(entry for entry in files if isinstance(entry, str) and entry.strip())


def _jsonl_objects(text: str) -> list[Mapping[str, Any]] | None:
    """Return one object per non-empty line, or None if any line is not a JSON object."""
    objects: list[Mapping[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            return None
        if not isinstance(value, Mapping):
            return None
        objects.append(value)
    return objects or None
