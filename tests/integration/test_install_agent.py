"""install-agent and uninstall-agent (docs/07 sections 3.3 and 3.4, docs/05)."""

import os
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from gitwhy.adapters.skill import (
    MARKER_FILENAME,
    PROJECT_SKILL_DIRS,
    _dir_if_skill,
    _read_template,
    agents_block,
    agents_template_text,
    bundled_skill_dir,
    install_agents_file,
    mcp_text,
)
from gitwhy.adapters.skill import (
    user_skill_dir as home_skill_dir,
)
from gitwhy.cli import app
from gitwhy.errors import CorruptError
from gitwhy.hooks import BEGIN_MARKER, END_MARKER
from tests.conftest import plain

runner = CliRunner()
ROOT = Path(__file__).resolve().parents[2]


def _git(repo: Path, *args: str) -> None:
    subprocess.run(  # noqa: S603
        ["git", "-C", str(repo), *args],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture(autouse=True)
def claude_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Keep ``--claude`` off the real home directory."""
    dest = tmp_path / "claude-home" / ".claude" / "skills" / "gitwhy"
    monkeypatch.setattr("gitwhy.adapters.skill.user_skill_dir", lambda: dest)
    return dest


@pytest.fixture
def repo(git_repo: Path) -> Path:
    _git(git_repo, "config", "user.name", "Test Human")
    _git(git_repo, "config", "user.email", "test@example.com")
    return git_repo


def _cli(repo: Path, monkeypatch: pytest.MonkeyPatch, *args: str) -> Result:
    monkeypatch.chdir(repo)
    return runner.invoke(app, list(args))


def test_template_is_short_and_states_the_rules() -> None:
    text = (ROOT / "templates" / "AGENTS.gitwhy.md").read_text(encoding="utf-8")
    assert len(text.splitlines()) <= 40
    assert "gitwhy why path/to/file.py:88" in text
    assert 'gitwhy capture --goal "..." --pending' in text
    assert "gitwhy check" in text
    assert "Do not invent a why" in text
    assert "gitwhy affirm" in text
    assert ".agents/skills/gitwhy/SKILL.md" in text
    assert BEGIN_MARKER not in text


def test_default_install_is_idempotent_and_uninstall_keeps_user_text(
    repo: Path, monkeypatch: pytest.MonkeyPatch, claude_home: Path
) -> None:
    (repo / "AGENTS.md").write_text("# Project notes\n\nKeep this.\n", encoding="utf-8")
    first = _cli(repo, monkeypatch, "install-agent")
    assert first.exit_code == 0, first.output
    for rel in PROJECT_SKILL_DIRS:
        skill = repo / rel
        assert (skill / "SKILL.md").read_text(encoding="utf-8").startswith("---\n")
        assert (skill / MARKER_FILENAME).read_text(encoding="utf-8").startswith(BEGIN_MARKER)
        script = skill / "scripts" / "capture.sh"
        assert os.access(script, os.X_OK)
    agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert agents.count(BEGIN_MARKER) == 1
    assert agents.count(END_MARKER) == 1
    assert "# Project notes" in agents
    assert "Do not invent a why" in agents
    assert "mcpServers" in first.stdout
    assert ".mcp.json" in first.stdout
    assert ".cursor/mcp.json" in first.stdout
    assert "config.toml" in first.stdout
    assert not claude_home.exists()

    second = _cli(repo, monkeypatch, "install-agent")
    assert second.exit_code == 0, second.output
    assert (repo / "AGENTS.md").read_text(encoding="utf-8").count(BEGIN_MARKER) == 1
    assert "Nothing changed" in second.stdout

    notes = repo / ".agents" / "skills" / "gitwhy" / "notes.md"
    notes.write_text("user note\n", encoding="utf-8")
    (repo / ".claude" / "skills" / "gitwhy" / "SKILL.md").write_text("edited\n", encoding="utf-8")
    refreshed = _cli(repo, monkeypatch, "install-agent")
    assert refreshed.exit_code == 0, refreshed.output
    assert "Updated skill: .claude/skills/gitwhy" in refreshed.stdout
    installed = (repo / ".claude" / "skills" / "gitwhy" / "SKILL.md").read_text(encoding="utf-8")
    assert installed == (ROOT / "skills" / "gitwhy" / "SKILL.md").read_text(encoding="utf-8")

    removed = _cli(repo, monkeypatch, "uninstall-agent")
    assert removed.exit_code == 0, removed.output
    left = (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert BEGIN_MARKER not in left
    assert "Keep this." in left
    assert not (repo / ".claude" / "skills" / "gitwhy").exists()
    assert notes.is_file()
    assert notes.read_text(encoding="utf-8") == "user note\n"
    assert "prepare-commit-msg" not in removed.stdout


def test_flags_select_one_piece(
    repo: Path, monkeypatch: pytest.MonkeyPatch, claude_home: Path
) -> None:
    mcp_only = _cli(repo, monkeypatch, "install-agent", "--mcp")
    assert mcp_only.exit_code == 0, mcp_only.output
    assert mcp_only.stdout == mcp_text()
    assert not (repo / ".agents").exists()
    assert not (repo / "AGENTS.md").exists()

    skill_only = _cli(repo, monkeypatch, "install-agent", "--skill")
    assert skill_only.exit_code == 0, skill_only.output
    assert (repo / ".github" / "skills" / "gitwhy" / "SKILL.md").is_file()
    assert not (repo / "AGENTS.md").exists()
    assert "mcpServers" not in skill_only.stdout

    claude = _cli(repo, monkeypatch, "install-agent", "--claude")
    assert claude.exit_code == 0, claude.output
    assert (claude_home / "SKILL.md").is_file()
    assert "Installed skill:" in claude.stdout

    agents = _cli(repo, monkeypatch, "install-agent", "--agents-md")
    assert agents.exit_code == 0, agents.output
    assert "Created AGENTS.md" in agents.stdout
    assert (repo / "AGENTS.md").read_text(encoding="utf-8") == agents_block()


def test_uninstall_removes_a_file_that_held_only_the_block(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _cli(repo, monkeypatch, "install-agent", "--agents-md")
    result = _cli(repo, monkeypatch, "uninstall-agent")
    assert result.exit_code == 0, result.output
    assert not (repo / "AGENTS.md").exists()
    assert "held only gitwhy's block" in result.stdout
    again = _cli(repo, monkeypatch, "uninstall-agent")
    assert again.exit_code == 0, again.output
    assert "Nothing changed" in again.stdout


def test_hooks_flag_installs_and_uninstalls_the_commit_hook(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _cli(repo, monkeypatch, "install-agent", "--hooks")
    assert first.exit_code == 0, first.output
    hook = repo / ".git" / "hooks" / "prepare-commit-msg"
    assert BEGIN_MARKER in hook.read_text(encoding="utf-8")
    assert not (repo / ".git" / "hooks" / "pre-commit").exists()
    second = _cli(repo, monkeypatch, "install-agent", "--hooks")
    assert second.exit_code == 0, second.output
    assert "already installed" in second.stdout

    text = hook.read_text(encoding="utf-8").replace("gitwhy hook", "gitwhy HOOK", 1)
    hook.write_text(text, encoding="utf-8")
    updated = _cli(repo, monkeypatch, "install-agent", "--hooks")
    assert updated.exit_code == 0, updated.output
    assert "Updated gitwhy's block" in updated.stdout
    assert "gitwhy hook" in hook.read_text(encoding="utf-8")

    hook.write_text(hook.read_text(encoding="utf-8") + "\n# user hook line\n", encoding="utf-8")
    removed = _cli(repo, monkeypatch, "uninstall-agent")
    assert removed.exit_code == 0, removed.output
    assert hook.is_file()
    left = hook.read_text(encoding="utf-8")
    assert BEGIN_MARKER not in left
    assert "# user hook line" in left


def test_hooks_flag_refuses_a_foreign_hook(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    hook = repo / ".git" / "hooks" / "prepare-commit-msg"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("#!/bin/sh\necho foreign\n", encoding="utf-8")
    result = _cli(repo, monkeypatch, "install-agent", "--skill", "--hooks")
    assert result.exit_code == 5, result.output
    assert "not managed by gitwhy" in plain(result.stderr)
    assert hook.read_text(encoding="utf-8") == "#!/bin/sh\necho foreign\n"
    assert (repo / ".agents" / "skills" / "gitwhy" / "SKILL.md").is_file()


def test_hooks_flag_refuses_when_hooks_path_is_set(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _git(repo, "config", "core.hooksPath", ".husky")
    result = _cli(repo, monkeypatch, "install-agent", "--hooks")
    assert result.exit_code == 5, result.output
    assert "core.hooksPath is set" in plain(result.stderr)
    assert not (repo / ".husky").exists()


def test_install_agent_outside_a_repo_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["install-agent"])
    assert result.exit_code == 2, result.output


def test_missing_skill_bundle_exits_4(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def missing() -> Path:
        raise CorruptError("The gitwhy skill is missing from this installation.")

    monkeypatch.setattr("gitwhy.adapters.skill.bundled_skill_dir", missing)
    result = _cli(repo, monkeypatch, "install-agent", "--skill")
    assert result.exit_code == 4, result.output
    assert "missing from this installation" in plain(result.output)


def test_help_lists_flags_and_exit_codes() -> None:
    result = runner.invoke(app, ["install-agent", "--help"])
    assert result.exit_code == 0, result.output
    text = plain(result.stdout)
    for flag in ("--claude", "--skill", "--mcp", "--agents-md", "--hooks"):
        assert flag in text
    assert "Exits 2" in text
    assert "5" in text
    uninstall = runner.invoke(app, ["uninstall-agent", "--help"])
    assert uninstall.exit_code == 0, uninstall.output
    assert "Exits 2" in plain(uninstall.stdout)


def test_bundle_lookup_and_agents_refresh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert bundled_skill_dir() == ROOT / "skills" / "gitwhy"
    assert agents_template_text() == (ROOT / "templates" / "AGENTS.gitwhy.md").read_text(
        encoding="utf-8"
    )
    empty = tmp_path / "empty"
    empty.mkdir()
    assert _dir_if_skill(empty) is None
    assert _read_template(tmp_path / "missing.md") is None
    (tmp_path / "SKILL.md").write_text("x\n", encoding="utf-8")
    assert _dir_if_skill(tmp_path) == tmp_path

    monkeypatch.setattr("gitwhy.adapters.skill._dir_if_skill", lambda _path: None)
    with pytest.raises(CorruptError):
        bundled_skill_dir()

    packaged = tmp_path / "gitwhy-skill"
    packaged.mkdir()
    (packaged / "SKILL.md").write_text("skill\n", encoding="utf-8")
    calls = {"n": 0}

    def fake_dir(path: Path) -> Path | None:
        calls["n"] += 1
        if calls["n"] == 1:
            return None
        return packaged

    monkeypatch.setattr("gitwhy.adapters.skill._dir_if_skill", fake_dir)
    assert bundled_skill_dir() == packaged

    monkeypatch.setattr("gitwhy.adapters.skill._read_template", lambda _path: None)

    class _Packaged:
        def joinpath(self, _name: str) -> "_Packaged":
            return self

        def read_text(self, encoding: str) -> str:
            assert encoding == "utf-8"
            return "from wheel\n"

    monkeypatch.setattr("gitwhy.adapters.skill.files", lambda _pkg: _Packaged())
    assert agents_template_text() == "from wheel\n"

    class _Missing:
        def joinpath(self, _name: str) -> "_Missing":
            raise OSError("missing")

    monkeypatch.setattr("gitwhy.adapters.skill.files", lambda _pkg: _Missing())
    with pytest.raises(CorruptError):
        agents_template_text()


def test_agents_block_is_refreshed_in_place(tmp_path: Path) -> None:
    path = tmp_path / "AGENTS.md"
    path.write_text("\n\n", encoding="utf-8")
    _, status = install_agents_file(tmp_path)
    assert status.value == "updated"
    path.write_text("# mine\n\n" + agents_block().replace(f"{END_MARKER}\n", ""), encoding="utf-8")
    _, status = install_agents_file(tmp_path)
    assert status.value == "updated"
    text = path.read_text(encoding="utf-8")
    assert text.count(BEGIN_MARKER) == 1
    assert text.count(END_MARKER) == 1
    assert text.startswith("# mine\n")
    _, status = install_agents_file(tmp_path)
    assert status.value == "unchanged"


def test_user_skill_dir_lives_under_the_home_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert home_skill_dir() == tmp_path / ".claude" / "skills" / "gitwhy"


def test_uninstall_leaves_an_unmanaged_agents_file(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (repo / "AGENTS.md").write_text("# just notes\n", encoding="utf-8")
    result = _cli(repo, monkeypatch, "uninstall-agent")
    assert result.exit_code == 0, result.output
    assert (repo / "AGENTS.md").read_text(encoding="utf-8") == "# just notes\n"
    assert "Nothing changed" in result.stdout


def test_uninstall_deletes_a_hook_that_only_held_gitwhy(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed = _cli(repo, monkeypatch, "install-agent", "--hooks")
    assert installed.exit_code == 0, installed.output
    removed = _cli(repo, monkeypatch, "uninstall-agent")
    assert removed.exit_code == 0, removed.output
    assert not (repo / ".git" / "hooks" / "prepare-commit-msg").exists()
    assert "held only gitwhy's block" in removed.stdout


def test_user_skill_uninstall_reports_the_home_copy(
    repo: Path, monkeypatch: pytest.MonkeyPatch, claude_home: Path
) -> None:
    installed = _cli(repo, monkeypatch, "install-agent", "--claude")
    assert installed.exit_code == 0, installed.output
    removed = _cli(repo, monkeypatch, "uninstall-agent")
    assert removed.exit_code == 0, removed.output
    assert not claude_home.exists()
    assert "Removed" in removed.stdout
