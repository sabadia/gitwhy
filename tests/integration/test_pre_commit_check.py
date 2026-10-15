"""Optional pre-commit check hook (docs/03 section 4 ``install-hooks --check``, docs/04 3.6)."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner, Result

from tests.conftest import plain
from whyline.check import CAPTURE_COMMAND
from whyline.cli import app
from whyline.config import enable_hook_check, load_config, project_config_path
from whyline.gitio import commit_message, whyline_ids
from whyline.hooks import PRE_COMMIT, managed_block
from whyline.store import initialize

runner = CliRunner()
VENV_BIN = str(Path(sys.executable).parent)


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(  # noqa: S603
        ["git", "-C", str(repo), *args],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


@pytest.fixture
def repo(git_repo: Path) -> Path:
    _git(git_repo, "config", "user.name", "Test Human")
    _git(git_repo, "config", "user.email", "test@example.com")
    _git(git_repo, "config", "commit.gpgsign", "false")
    initialize(git_repo)
    (git_repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(git_repo, "add", "-A")
    _git(git_repo, "commit", "-q", "-m", "base")
    return git_repo


def _cli(repo: Path, monkeypatch: pytest.MonkeyPatch, *args: str) -> Result:
    monkeypatch.chdir(repo)
    return runner.invoke(app, list(args))


def _stage(repo: Path, name: str, lines: int) -> None:
    (repo / name).write_text("".join(f"line {i}\n" for i in range(lines)), encoding="utf-8")
    _git(repo, "add", name)


def _commit(
    repo: Path, message: str, *extra: str, with_whyline: bool = True
) -> subprocess.CompletedProcess[str]:
    if with_whyline:
        path = VENV_BIN + os.pathsep + os.environ["PATH"]
    else:
        git_dir = str(Path(shutil.which("git") or "/usr/bin/git").parent)
        path = os.pathsep.join(dict.fromkeys([git_dir, "/usr/bin", "/bin"]))
    return subprocess.run(  # noqa: S603
        ["git", "-C", str(repo), "commit", "-q", "-m", message, *extra],  # noqa: S607
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": path},
        check=False,
    )


def _pre_commit(repo: Path) -> Path:
    return repo / ".git" / "hooks" / PRE_COMMIT


# --- installing ---------------------------------------------------------------------------------


def test_off_by_default(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _cli(repo, monkeypatch, "install-hooks")
    assert result.exit_code == 0
    assert not _pre_commit(repo).exists()
    assert load_config(repo).hooks.check is False
    _stage(repo, "big.py", 100)
    assert _commit(repo, "big, unlinked").returncode == 0


def test_check_flag_installs_both_hooks_and_turns_it_on(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _cli(repo, monkeypatch, "install-hooks", "--check")
    assert result.exit_code == 0, result.output
    text = plain(result.output)
    assert "Installed prepare-commit-msg hook" in text
    assert "Installed pre-commit hook: .git/hooks/pre-commit" in text
    assert "Turned on the pre-commit check" in text
    assert managed_block(PRE_COMMIT) in _pre_commit(repo).read_text(encoding="utf-8")
    config_text = project_config_path(repo).read_text(encoding="utf-8")
    assert config_text.startswith("# Whyline project config.")  # comments survive
    assert yaml.safe_load(config_text) == {"schema_version": 1, "hooks": {"check": True}}


def test_check_flag_twice_is_idempotent(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _cli(repo, monkeypatch, "install-hooks", "--check")
    hook_before = _pre_commit(repo).read_text(encoding="utf-8")
    config_before = project_config_path(repo).read_text(encoding="utf-8")
    result = _cli(repo, monkeypatch, "install-hooks", "--check")
    assert result.exit_code == 0
    assert "already on" in plain(result.output)
    assert _pre_commit(repo).read_text(encoding="utf-8") == hook_before
    assert project_config_path(repo).read_text(encoding="utf-8") == config_before


def test_foreign_pre_commit_is_refused_but_the_rest_installs(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hook = _pre_commit(repo)
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("#!/bin/sh\nexec make lint\n", encoding="utf-8")
    result = _cli(repo, monkeypatch, "install-hooks", "--check")
    assert result.exit_code == 5
    assert hook.read_text(encoding="utf-8") == "#!/bin/sh\nexec make lint\n"
    assert "# Add to .git/hooks/pre-commit:" in result.stdout
    assert managed_block(PRE_COMMIT) in result.stdout
    assert (repo / ".git" / "hooks" / "prepare-commit-msg").exists()
    assert load_config(repo).hooks.check is True


def test_uninstall_removes_both_blocks(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _cli(repo, monkeypatch, "install-hooks", "--check")
    result = _cli(repo, monkeypatch, "uninstall-hooks")
    assert result.exit_code == 0
    assert not _pre_commit(repo).exists()
    assert not (repo / ".git" / "hooks" / "prepare-commit-msg").exists()
    assert "Removed .git/hooks/pre-commit" in plain(result.output)


# --- committing through the hook ------------------------------------------------------------------


@pytest.fixture
def checked(repo: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    assert _cli(repo, monkeypatch, "install-hooks", "--check").exit_code == 0
    _git(repo, "add", ".whyline")
    _git(repo, "commit", "-q", "-m", "turn on the check")
    return repo


def test_large_unlinked_commit_is_blocked_with_the_capture_command(checked: Path) -> None:
    head = _git(checked, "rev-parse", "HEAD")
    _stage(checked, "big.py", 40)
    completed = _commit(checked, "big, unlinked")
    assert completed.returncode != 0
    assert CAPTURE_COMMAND in completed.stderr
    assert "--no-verify" in completed.stderr
    assert _git(checked, "rev-parse", "HEAD") == head


def test_capture_pending_unblocks_and_links_the_commit(
    checked: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stage(checked, "big.py", 40)
    captured = _cli(checked, monkeypatch, "capture", "--goal", "Big but explained", "--pending")
    assert captured.exit_code == 0, captured.output
    completed = _commit(checked, "big, explained")
    assert completed.returncode == 0, completed.stderr
    assert len(whyline_ids(commit_message("HEAD", checked), checked)) == 1


def test_small_commit_passes(checked: Path) -> None:
    _stage(checked, "small.py", 5)
    assert _commit(checked, "small").returncode == 0


def test_no_verify_skips_the_check(checked: Path) -> None:
    _stage(checked, "big.py", 40)
    assert _commit(checked, "big", "--no-verify").returncode == 0


def test_turning_the_check_off_in_config_lets_commits_through(checked: Path) -> None:
    path = project_config_path(checked)
    path.write_text(path.read_text(encoding="utf-8").replace("check: true", "check: false"))
    _stage(checked, "big.py", 40)
    assert _commit(checked, "big").returncode == 0


def test_check_enabled_also_turns_the_hook_on(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _cli(repo, monkeypatch, "install-hooks", "--check")
    project_config_path(repo).write_text("schema_version: 1\ncheck:\n  enabled: true\n")
    _stage(repo, "big.py", 40)
    assert _commit(repo, "big").returncode != 0


def test_commit_goes_through_when_whyline_is_missing(checked: Path) -> None:
    _stage(checked, "big.py", 40)
    completed = _commit(checked, "big", with_whyline=False)
    assert completed.returncode == 0, completed.stderr
    assert "whyline: not found on PATH; skipping whyline check" in completed.stderr


def test_commit_goes_through_when_the_check_breaks(checked: Path) -> None:
    project_config_path(checked).write_text("check: [broken\n", encoding="utf-8")
    _stage(checked, "big.py", 40)
    completed = _commit(checked, "big")
    assert completed.returncode == 0, completed.stderr
    assert "whyline: skipped the check" in completed.stderr


# --- the hook step and the config toggle directly ---------------------------------------------


def test_hook_step_exit_codes(checked: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert _cli(checked, monkeypatch, "hook", "pre-commit").exit_code == 0
    _stage(checked, "big.py", 40)
    blocked = _cli(checked, monkeypatch, "hook", "pre-commit")
    assert blocked.exit_code == 3
    assert CAPTURE_COMMAND in plain(blocked.stderr)


def test_hook_step_never_blocks_on_its_own_failure(
    checked: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_config_path(checked).write_text("check: [broken\n", encoding="utf-8")
    result = _cli(checked, monkeypatch, "hook", "pre-commit")
    assert result.exit_code == 0
    assert "whyline: skipped the check" in plain(result.stderr)


def test_hook_step_is_quiet_when_off(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stage(repo, "big.py", 40)
    result = _cli(repo, monkeypatch, "hook", "pre-commit")
    assert result.exit_code == 0
    assert result.output == ""


def test_enable_keeps_other_hook_settings(repo: Path) -> None:
    project_config_path(repo).write_text("schema_version: 1\nhooks:\n  trailer: false\n")
    assert enable_hook_check(repo) is True
    config = load_config(repo)
    assert config.hooks.check is True and config.hooks.trailer is False
    assert enable_hook_check(repo) is False


def test_enable_without_a_config_file(repo: Path) -> None:
    project_config_path(repo).unlink()
    assert enable_hook_check(repo) is True
    assert load_config(repo).hooks.check is True


def test_enable_appends_after_a_file_without_trailing_newline(repo: Path) -> None:
    project_config_path(repo).write_text("schema_version: 1", encoding="utf-8")
    enable_hook_check(repo)
    assert project_config_path(repo).read_text() == "schema_version: 1\nhooks:\n  check: true\n"
