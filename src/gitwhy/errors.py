"""Typed error hierarchy and stable exit codes (docs/03 section 3)."""

from enum import IntEnum
from typing import ClassVar


class ExitCode(IntEnum):
    """Process exit codes. These are part of the public API; never renumber them."""

    OK = 0
    USAGE = 1
    NO_REPO = 2
    CHECK_FAILED = 3
    CORRUPT = 4
    HOOK_CONFLICT = 5
    SCHEMA = 6
    UNSAFE_GIT = 7
    AFFIRM_REFUSED = 8
    NOT_FOUND = 9


class GitwhyError(Exception):
    """Base class for every error gitwhy reports to the user.

    ``message`` says what happened and names the path or id involved. ``hint`` is the next
    command to run, when there is one (docs/03 section 8).
    """

    exit_code: ClassVar[ExitCode] = ExitCode.USAGE

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint

    def __str__(self) -> str:
        return self.message if self.hint is None else f"{self.message} {self.hint}"


class UsageError(GitwhyError):
    """Bad arguments."""

    exit_code = ExitCode.USAGE


class NoRepoError(GitwhyError):
    """Not a git repository, or gitwhy is not initialized where it is required."""

    exit_code = ExitCode.NO_REPO


class CheckFailedError(GitwhyError):
    """The change needs a record and has none."""

    exit_code = ExitCode.CHECK_FAILED


class CorruptError(GitwhyError):
    """A record or config file failed to parse or validate."""

    exit_code = ExitCode.CORRUPT


class HookConflictError(GitwhyError):
    """Refusing to overwrite a hook gitwhy does not manage."""

    exit_code = ExitCode.HOOK_CONFLICT


class SchemaVersionError(GitwhyError):
    """A file uses a schema version newer than this gitwhy supports."""

    exit_code = ExitCode.SCHEMA


class UnsafeGitError(GitwhyError):
    """Refusing a git operation that could rewrite published history."""

    exit_code = ExitCode.UNSAFE_GIT


class AffirmRefusedError(GitwhyError):
    """Affirm attempted without passing the human gate."""

    exit_code = ExitCode.AFFIRM_REFUSED


class NotFoundError(GitwhyError):
    """A record id or path does not exist."""

    exit_code = ExitCode.NOT_FOUND
