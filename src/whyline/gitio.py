"""Local git queries. Only runs the local ``git`` binary; never touches the network."""

import shutil
import subprocess
from pathlib import Path

from whyline.errors import NoRepoError, UsageError

WHYLINE_PREFIX = ".whyline/"


def _git_executable() -> str:
    git = shutil.which("git")
    if git is None:
        raise NoRepoError(
            "git is not installed or not on PATH.", hint="Install git and run the command again."
        )
    return git


def repo_root(start: Path) -> Path:
    """Return the top-level directory of the git work tree containing ``start``."""
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell, local git only
        [_git_executable(), "rev-parse", "--show-toplevel"],
        cwd=start,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise NoRepoError(
            f"Not inside a git work tree: {start}.",
            hint="Run `git init` first, or run whyline inside a git repository.",
        )
    return Path(completed.stdout.strip())


def config_value(key: str, cwd: Path) -> str | None:
    """Return ``git config --get <key>`` as seen from ``cwd``, or None when it is unset."""
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell, local git only
        [_git_executable(), "config", "--get", key],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return value or None


def staged_paths(root: Path) -> list[str]:
    """Return repo-relative POSIX paths in the index that differ from HEAD.

    Works in a repository with no commits yet. Paths under ``.whyline/`` are left out: a record
    never explains whyline's own files.
    """
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell, local git only
        [_git_executable(), "diff", "--cached", "--name-only", "-z"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise NoRepoError(f"Cannot list staged files in {root}: {detail}.")
    try:
        names = completed.stdout.decode("utf-8")
    except UnicodeDecodeError:
        raise UsageError(
            "Some staged file names are not valid UTF-8.", hint="Pass the files with --file."
        ) from None
    return [
        name
        for name in names.split("\0")
        if name and name != WHYLINE_PREFIX.rstrip("/") and not name.startswith(WHYLINE_PREFIX)
    ]
