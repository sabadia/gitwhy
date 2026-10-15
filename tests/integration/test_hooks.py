"""Hook installer and the prepare-commit-msg step (docs/03 section 4, docs/05 section 2)."""

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from intentline.cli import app
from intentline.errors import NoRepoError
from intentline.gitio import commit_message, git_path, intentline_ids
from intentline.hooks import (
    BEGIN_MARKER,
    END_MARKER,
    MARKER,
    InstallStatus,
    apply_pending_trailer,
    install_hook,
    managed_block,
)
from intentline.store import RecordStore, initialize, write_pending
from tests.conftest import MakeRecord, plain, uuid7

runner = CliRunner()
VENV_BIN = str(Path(sys.executable).parent)


def _git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(  # noqa: S603
        ["git", "-C", str(repo), *args],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return completed.stdout.strip()


@pytest.fixture
def repo(git_repo: Path, make_record: MakeRecord) -> Path:
    _git(git_repo, "config", "user.name", "Test Human")
    _git(git_repo, "config", "user.email", "test@example.com")
    _git(git_repo, "config", "commit.gpgsign", "false")
    initialize(git_repo)
    RecordStore(git_repo / ".intentline").save(make_record(1))
    return git_repo


def _hook(repo: Path) -> Path:
    return repo / ".git" / "hooks" / "prepare-commit-msg"


def _cli(repo: Path, monkeypatch: pytest.MonkeyPatch, *args: str) -> Result:
    monkeypatch.chdir(repo)
    return runner.invoke(app, list(args))


def _commit(repo: Path, message: str, *, path_env: str) -> subprocess.CompletedProcess[str]:
    (repo / "change.txt").write_text(message, encoding="utf-8")
    _git(repo, "add", "change.txt")
    env = {**os.environ, "PATH": path_env}
    return subprocess.run(  # noqa: S603
        ["git", "-C", str(repo), "commit", "-q", "-m", message],  # noqa: S607
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def _path_with_intentline() -> str:
    return VENV_BIN + os.pathsep + os.environ["PATH"]


def _path_without_intentline() -> str:
    git_dir = str(Path(shutil.which("git") or "/usr/bin/git").parent)
    return os.pathsep.join(dict.fromkeys([git_dir, "/usr/bin", "/bin"]))


# --- docs/05 required ---------------------------------------------------------------------------


def test_install_creates_executable_hook(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _cli(repo, monkeypatch, "install-hooks")
    assert result.exit_code == 0, result.output
    hook = _hook(repo)
    text = hook.read_text(encoding="utf-8")
    assert text.startswith("#!/bin/sh\n")
    assert managed_block() in text
    assert hook.stat().st_mode & stat.S_IXUSR
    assert "Installed prepare-commit-msg hook: .git/hooks/prepare-commit-msg" in plain(
        result.output
    )


def test_install_twice_leaves_one_managed_block(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _cli(repo, monkeypatch, "install-hooks")
    first = _hook(repo).read_text(encoding="utf-8")
    result = _cli(repo, monkeypatch, "install-hooks")
    assert result.exit_code == 0
    assert "Nothing changed" in plain(result.output)
    text = _hook(repo).read_text(encoding="utf-8")
    assert text == first
    assert text.count(BEGIN_MARKER) == 1 and text.count(END_MARKER) == 1


def test_install_refuses_foreign_hook_exit_5_file_unchanged(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hook = _hook(repo)
    hook.parent.mkdir(parents=True, exist_ok=True)
    foreign = "#!/bin/sh\necho 'my own hook'\n"
    hook.write_text(foreign, encoding="utf-8")
    result = _cli(repo, monkeypatch, "install-hooks")
    assert result.exit_code == 5
    assert hook.read_text(encoding="utf-8") == foreign
    assert managed_block() in result.stdout, "the snippet to add by hand goes to stdout"
    assert "not managed by intentline" in plain(result.stderr)


def test_uninstall_removes_block_and_keeps_user_lines(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _cli(repo, monkeypatch, "install-hooks")
    hook = _hook(repo)
    hook.write_text(hook.read_text(encoding="utf-8") + "echo 'user line after'\n", encoding="utf-8")
    result = _cli(repo, monkeypatch, "uninstall-hooks")
    assert result.exit_code == 0
    text = hook.read_text(encoding="utf-8")
    assert MARKER not in text
    assert "echo 'user line after'" in text
    assert text.startswith("#!/bin/sh\n")
    assert "your other lines are unchanged" in plain(result.output)


# --- installer details ------------------------------------------------------------------------


def test_uninstall_deletes_a_file_holding_only_our_block(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _cli(repo, monkeypatch, "install-hooks")
    result = _cli(repo, monkeypatch, "uninstall-hooks")
    assert result.exit_code == 0
    assert not _hook(repo).exists()
    assert "Removed .git/hooks/prepare-commit-msg" in plain(result.output)


@pytest.mark.parametrize("state", ["missing", "foreign"])
def test_uninstall_when_not_installed_changes_nothing(
    repo: Path, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    hook = _hook(repo)
    if state == "foreign":
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
    result = _cli(repo, monkeypatch, "uninstall-hooks")
    assert result.exit_code == 0
    assert "Nothing changed" in plain(result.output)
    if state == "foreign":
        assert hook.read_text(encoding="utf-8") == "#!/bin/sh\necho mine\n"


def test_install_refreshes_an_outdated_block_and_keeps_user_lines(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hook = _hook(repo)
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(
        f"#!/bin/sh\necho before\n{BEGIN_MARKER} old\nold body\n{END_MARKER}\necho after\n",
        encoding="utf-8",
    )
    result = _cli(repo, monkeypatch, "install-hooks")
    assert result.exit_code == 0
    assert "Updated intentline's block" in plain(result.output)
    text = hook.read_text(encoding="utf-8")
    assert text == f"#!/bin/sh\necho before\n{managed_block()}echo after\n"
    assert hook.stat().st_mode & stat.S_IXUSR


def test_install_restores_a_lost_executable_bit(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _cli(repo, monkeypatch, "install-hooks")
    _hook(repo).chmod(0o644)
    assert install_hook(repo).status is InstallStatus.UPDATED
    assert _hook(repo).stat().st_mode & stat.S_IXUSR


def test_block_without_end_marker_is_replaced_to_end_of_file(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hook = _hook(repo)
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(f"#!/bin/sh\n{BEGIN_MARKER}\ntruncated\n", encoding="utf-8")
    _cli(repo, monkeypatch, "install-hooks")
    assert hook.read_text(encoding="utf-8") == f"#!/bin/sh\n{managed_block()}"


def test_core_hooks_path_set_writes_nothing_and_exits_5(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _git(repo, "config", "core.hooksPath", ".husky")
    result = _cli(repo, monkeypatch, "install-hooks")
    assert result.exit_code == 5
    assert managed_block() in result.stdout
    assert "core.hooksPath is set" in plain(result.stderr)
    assert ".husky/prepare-commit-msg" in plain(result.stderr)
    assert not (repo / ".husky").exists()
    assert not _hook(repo).exists()


def test_install_outside_repo_exits_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plain_dir = tmp_path / "plain"
    plain_dir.mkdir()
    assert _cli(plain_dir, monkeypatch, "install-hooks").exit_code == 2
    assert _cli(plain_dir, monkeypatch, "uninstall-hooks").exit_code == 2


def test_template_ships_with_the_package() -> None:
    block = managed_block()
    assert block.startswith(BEGIN_MARKER)
    assert block.rstrip("\n").endswith(END_MARKER)
    assert "curl" not in block and "wget" not in block  # docs/05: hooks never touch the network


# --- real commits through the installed hook ----------------------------------------------------


def test_commit_gets_pending_trailer_and_pending_is_cleared(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _cli(repo, monkeypatch, "install-hooks")
    write_pending(repo / ".intentline", uuid7(1))
    completed = _commit(repo, "Close invoices daily", path_env=_path_with_intentline())
    assert completed.returncode == 0, completed.stderr
    message = commit_message("HEAD", repo)
    assert intentline_ids(message, repo) == [uuid7(1)]
    assert message.startswith("Close invoices daily\n\nIntentline-Id: ")
    assert not (repo / ".intentline" / "pending").exists()
    assert f"added Intentline-Id: {uuid7(1)}" in completed.stderr


def test_commit_without_pending_is_untouched(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _cli(repo, monkeypatch, "install-hooks")
    completed = _commit(repo, "Plain change", path_env=_path_with_intentline())
    assert completed.returncode == 0, completed.stderr
    assert commit_message("HEAD", repo) == "Plain change\n"


def test_existing_trailer_is_kept_and_pending_survives(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _cli(repo, monkeypatch, "install-hooks")
    write_pending(repo / ".intentline", uuid7(1))
    completed = _commit(
        repo, f"Already linked\n\nIntentline-Id: {uuid7(7)}", path_env=_path_with_intentline()
    )
    assert completed.returncode == 0, completed.stderr
    assert intentline_ids(commit_message("HEAD", repo), repo) == [uuid7(7)]
    assert (repo / ".intentline" / "pending").read_text() == f"{uuid7(1)}\n"


def test_commit_succeeds_when_intentline_is_not_on_path(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _cli(repo, monkeypatch, "install-hooks")
    write_pending(repo / ".intentline", uuid7(1))
    completed = _commit(repo, "No intentline here", path_env=_path_without_intentline())
    assert completed.returncode == 0, completed.stderr
    assert "intentline: not found on PATH" in completed.stderr
    assert commit_message("HEAD", repo) == "No intentline here\n"
    assert (repo / ".intentline" / "pending").exists()


def test_commit_succeeds_when_the_hook_step_fails(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _cli(repo, monkeypatch, "install-hooks")
    write_pending(repo / ".intentline", uuid7(1))
    (repo / ".intentline" / "pending").chmod(0o000)
    try:
        completed = _commit(repo, "Unreadable pending", path_env=_path_with_intentline())
    finally:
        (repo / ".intentline" / "pending").chmod(0o644)
    assert completed.returncode == 0, completed.stderr
    if os.geteuid() != 0:  # root can read the file anyway
        assert "could not add a Intentline-Id trailer" in completed.stderr


# --- the hook step directly ---------------------------------------------------------------------


def test_hook_command_with_relative_message_file(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_pending(repo / ".intentline", uuid7(1))
    (repo / ".git" / "COMMIT_EDITMSG").write_text("Subject\n", encoding="utf-8")
    result = _cli(repo, monkeypatch, "hook", "prepare-commit-msg", ".git/COMMIT_EDITMSG", "message")
    assert result.exit_code == 0
    text = (repo / ".git" / "COMMIT_EDITMSG").read_text(encoding="utf-8")
    assert intentline_ids(text, repo) == [uuid7(1)]


def test_hook_command_never_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plain_dir = tmp_path / "plain"
    plain_dir.mkdir()
    result = _cli(plain_dir, monkeypatch, "hook", "prepare-commit-msg", "MSG")
    assert result.exit_code == 0
    assert "could not add a Intentline-Id trailer" in plain(result.stderr)


def test_hook_command_is_hidden_from_help(monkeypatch: pytest.MonkeyPatch, repo: Path) -> None:
    result = _cli(repo, monkeypatch, "--help")
    assert "install-hooks" in result.stdout
    assert "Entry points called by installed git hooks" not in result.stdout


def test_apply_pending_trailer_without_init(git_repo: Path) -> None:
    message = git_repo / "MSG"
    message.write_text("Subject\n", encoding="utf-8")
    assert apply_pending_trailer(git_repo, message) is None
    assert message.read_text(encoding="utf-8") == "Subject\n"


def test_hooks_path_outside_repo_is_shown_absolute(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_hooks = tmp_path / "global-hooks"
    _git(repo, "config", "core.hooksPath", str(global_hooks))
    result = _cli(repo, monkeypatch, "install-hooks")
    assert result.exit_code == 5
    joined = "".join(plain(result.stderr).split())  # Rich may wrap a long absolute path
    assert "".join(str(global_hooks / "prepare-commit-msg").split()) in joined
    assert ".git/hooks" not in joined
    assert not global_hooks.exists()


def test_git_path_outside_a_repository(tmp_path: Path) -> None:
    plain_dir = tmp_path / "plain"
    plain_dir.mkdir()
    with pytest.raises(NoRepoError):
        git_path("hooks", plain_dir)


def test_apply_pending_trailer_keeps_existing_link(repo: Path) -> None:
    write_pending(repo / ".intentline", uuid7(1))
    message = repo / "MSG"
    message.write_text(f"Subject\n\nIntentline-Id: {uuid7(7)}\n", encoding="utf-8")
    assert apply_pending_trailer(repo, message) is None
    assert message.read_text(encoding="utf-8") == f"Subject\n\nIntentline-Id: {uuid7(7)}\n"
    assert (repo / ".intentline" / "pending").exists()
