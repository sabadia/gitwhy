"""Install and remove whyline's git hooks, and run the prepare-commit-msg step (docs/03 §4).

Hook scripts are POSIX sh. Whyline owns only the lines between its ``# whyline-managed``
markers; anything else in a hook file belongs to the user and is never changed.
"""

import os
from dataclasses import dataclass
from enum import StrEnum
from importlib.resources import files
from pathlib import Path

from whyline.check import CheckResult, run_check
from whyline.config import load_config
from whyline.gitio import add_whyline_trailer, config_value, git_path, whyline_ids
from whyline.store import PENDING_FILENAME, WHYLINE_DIRNAME, read_pending

MARKER = "# whyline-managed"
BEGIN_MARKER = f"{MARKER}: begin"
END_MARKER = f"{MARKER}: end"
SHEBANG = "#!/bin/sh"
PREPARE_COMMIT_MSG = "prepare-commit-msg"
PRE_COMMIT = "pre-commit"
MANAGED_HOOKS = (PREPARE_COMMIT_MSG, PRE_COMMIT)


def managed_block(hook: str = PREPARE_COMMIT_MSG) -> str:
    """Return whyline's block for ``hook``, from the template shipped with the package."""
    return files(__package__).joinpath(f"{hook}.sh").read_text(encoding="utf-8")


class InstallStatus(StrEnum):
    """Outcome of installing one hook."""

    CREATED = "created"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    FOREIGN = "foreign"
    HOOKS_PATH = "hooks_path"


@dataclass(frozen=True)
class HookResult:
    """What happened to one hook file. ``snippet`` is what to add by hand when refused."""

    hook: str
    path: Path
    status: InstallStatus
    snippet: str = ""


def hooks_dir(root: Path) -> Path:
    """Return the directory git runs hooks from (honours worktrees and ``core.hooksPath``)."""
    return git_path("hooks", root)


def _split_block(text: str) -> tuple[list[str], list[str], list[str]] | None:
    """Return (before, block, after) lines around the managed block, or None if absent."""
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith(BEGIN_MARKER)]
    if not starts:
        return None
    start = starts[0]
    ends = [i for i, line in enumerate(lines) if i > start and line.startswith(END_MARKER)]
    end = ends[0] if ends else len(lines) - 1
    return lines[:start], lines[start : end + 1], lines[end + 1 :]


def _write_executable(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.whyline.tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.chmod(0o755)
    tmp.replace(path)


def install_hook(root: Path, hook: str = PREPARE_COMMIT_MSG) -> HookResult:
    """Install or refresh whyline's block in ``hook``. Never overwrites a foreign hook.

    - ``core.hooksPath`` set: nothing is written; the result carries the block to add there.
    - No hook file: a new one is created with a shebang and the block.
    - A file with the block: the block is replaced in place; everything else is kept.
    - A file without the block (someone else's hook): nothing is written.
    """
    block = managed_block(hook)
    path = hooks_dir(root) / hook
    if config_value("core.hooksPath", root) is not None:
        return HookResult(hook, path, InstallStatus.HOOKS_PATH, snippet=block)
    try:
        current = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        _write_executable(path, f"{SHEBANG}\n{block}")
        return HookResult(hook, path, InstallStatus.CREATED)
    parts = _split_block(current)
    if parts is None:
        return HookResult(hook, path, InstallStatus.FOREIGN, snippet=block)
    before, _, after = parts
    updated = "\n".join([*before, *block.splitlines(), *after]) + "\n"
    if updated == current and os.access(path, os.X_OK):
        return HookResult(hook, path, InstallStatus.UNCHANGED)
    _write_executable(path, updated)
    return HookResult(hook, path, InstallStatus.UPDATED)


class UninstallStatus(StrEnum):
    """Outcome of uninstalling one hook."""

    REMOVED_FILE = "removed_file"
    REMOVED_BLOCK = "removed_block"
    NOT_INSTALLED = "not_installed"


def uninstall_hook(root: Path, hook: str = PREPARE_COMMIT_MSG) -> tuple[Path, UninstallStatus]:
    """Remove whyline's block from ``hook``. Other lines stay; a file left empty is deleted."""
    path = hooks_dir(root) / hook
    try:
        current = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return path, UninstallStatus.NOT_INSTALLED
    parts = _split_block(current)
    if parts is None:
        return path, UninstallStatus.NOT_INSTALLED
    before, _, after = parts
    remaining = [*before, *after]
    if all(not line.strip() or line.strip() == SHEBANG for line in remaining):
        path.unlink()
        return path, UninstallStatus.REMOVED_FILE
    _write_executable(path, "\n".join(remaining) + "\n")
    return path, UninstallStatus.REMOVED_BLOCK


def apply_pending_trailer(root: Path, message_file: Path) -> str | None:
    """Add ``Whyline-Id`` from ``.whyline/pending`` to the commit message in ``message_file``.

    Does nothing when nothing is pending, or when the message already has a ``Whyline-Id``
    (an existing link is never replaced; pending is then kept for the next commit). After a
    trailer is added, pending is cleared. Returns the id that was added, if any.
    """
    whyline_dir = root / WHYLINE_DIRNAME
    record_id = read_pending(whyline_dir)
    if record_id is None:
        return None
    message = message_file.read_text(encoding="utf-8")
    if whyline_ids(message, root):
        return None
    updated = add_whyline_trailer(message, record_id, root)
    message_file.write_text(updated, encoding="utf-8")
    (whyline_dir / PENDING_FILENAME).unlink(missing_ok=True)
    return str(record_id)


def pre_commit_check(root: Path) -> CheckResult | None:
    """Run ``whyline check`` on the staged diff if the project turned the check on.

    Returns None when ``hooks.check`` and ``check.enabled`` are both false, so an installed hook
    stays quiet until a team opts in.
    """
    config = load_config(root)
    if not (config.hooks.check or config.check.enabled):
        return None
    return run_check(root)
