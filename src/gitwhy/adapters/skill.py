"""Install the portable skill and the AGENTS.md snippet (docs/07 sections 3.3 and 3.4).

The skill text lives once, at ``skills/gitwhy/`` in this repository (and, in a wheel,
under ``gitwhy/bundled``). Install copies that tree. It does not rewrite it.
"""

from dataclasses import dataclass
from enum import StrEnum
from importlib.resources import files
from pathlib import Path

from gitwhy.errors import CorruptError
from gitwhy.hooks import BEGIN_MARKER, END_MARKER

MARKER_FILENAME = ".gitwhy-managed"
"""Sidecar written into each installed skill copy so uninstall can tell it from user files."""

PROJECT_SKILL_DIRS = (
    Path(".claude/skills/gitwhy"),
    Path(".agents/skills/gitwhy"),
    Path(".github/skills/gitwhy"),
)
"""Project-relative copies. One skill text, three places agents look. Not the user home."""

AGENTS_FILENAME = "AGENTS.md"

MCP_SNIPPET = """\
{
  "mcpServers": {
    "gitwhy": {
      "command": "gitwhy-mcp"
    }
  }
}
"""

MCP_WHERE = (
    "Where to put it (gitwhy does not write this file):\n"
    "- Claude Code: `.mcp.json` in the project, or "
    "`claude mcp add --scope project gitwhy -- gitwhy-mcp`. "
    "User scope is `claude mcp add --scope user` (`~/.claude.json`).\n"
    "- Cursor: `.cursor/mcp.json` in the project, or `~/.cursor/mcp.json`. "
    'Same JSON. Add `"type": "stdio"` if Cursor asks for it.\n'
    "- Codex: `codex mcp add gitwhy -- gitwhy-mcp`, or "
    '`[mcp_servers.gitwhy]` with `command = "gitwhy-mcp"` '
    "in `.codex/config.toml` (trusted projects) or `~/.codex/config.toml`.\n"
    "The `gitwhy-mcp` command needs the optional extra: "
    "`uv tool install 'gitwhy[mcp]'`.\n"
)


class CopyStatus(StrEnum):
    """What an install did to one skill directory or to AGENTS.md."""

    CREATED = "created"
    UPDATED = "updated"
    UNCHANGED = "unchanged"


class RemoveStatus(StrEnum):
    """What an uninstall did to AGENTS.md."""

    REMOVED_FILE = "removed_file"
    REMOVED_BLOCK = "removed_block"
    NOT_INSTALLED = "not_installed"


@dataclass(frozen=True)
class SkillCopy:
    """One installed skill directory."""

    path: Path
    status: CopyStatus


@dataclass(frozen=True)
class AgentInstallPlan:
    """Which pieces ``install-agent`` should touch. All-false means the default set."""

    skill: bool = False
    claude_user: bool = False
    agents_md: bool = False
    mcp: bool = False

    @classmethod
    def from_flags(
        cls,
        *,
        skill: bool,
        claude_user: bool,
        agents_md: bool,
        mcp: bool,
        hooks: bool,
    ) -> "AgentInstallPlan":
        """Flags select pieces. No flags installs the project skill, AGENTS.md, and prints MCP."""
        if not any((skill, claude_user, agents_md, mcp, hooks)):
            return cls(skill=True, agents_md=True, mcp=True)
        return cls(skill=skill, claude_user=claude_user, agents_md=agents_md, mcp=mcp)


def user_skill_dir() -> Path:
    """Return ``~/.claude/skills/gitwhy``. ``--claude`` is the only flag that writes here."""
    return Path.home() / ".claude" / "skills" / "gitwhy"


def _dir_if_skill(path: Path) -> Path | None:
    if (path / "SKILL.md").is_file():
        return path
    return None


def bundled_skill_dir() -> Path:
    """Return the skill tree shipped with gitwhy.

    The repository copy wins, so an editable checkout installs the files just edited.
    A wheel falls through to ``gitwhy/bundled/gitwhy-skill``.
    """
    repo = _dir_if_skill(Path(__file__).resolve().parents[3] / "skills" / "gitwhy")
    if repo is not None:
        return repo
    packaged = _dir_if_skill(Path(str(files("gitwhy").joinpath("bundled/gitwhy-skill"))))
    if packaged is not None:
        return packaged
    raise CorruptError(
        "The gitwhy skill is missing from this installation.",
        hint="Reinstall gitwhy. The skill must be at skills/gitwhy/SKILL.md.",
    )


def _read_template(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def agents_template_text() -> str:
    """Return ``templates/AGENTS.gitwhy.md``, or the copy bundled in the wheel."""
    repo = Path(__file__).resolve().parents[3] / "templates" / "AGENTS.gitwhy.md"
    text = _read_template(repo)
    if text is not None:
        return text
    try:
        return files("gitwhy").joinpath("bundled/AGENTS.gitwhy.md").read_text(encoding="utf-8")
    except OSError as exc:
        raise CorruptError(
            "The AGENTS.md snippet is missing from this installation.",
            hint="Reinstall gitwhy. The snippet must be at templates/AGENTS.gitwhy.md.",
        ) from exc


def _skill_files(src: Path) -> list[Path]:
    return sorted(path.relative_to(src) for path in src.rglob("*") if path.is_file())


def _split_managed(text: str) -> tuple[list[str], list[str], list[str]] | None:
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith(BEGIN_MARKER)]
    if not starts:
        return None
    start = starts[0]
    ends = [i for i, line in enumerate(lines) if i > start and line.startswith(END_MARKER)]
    end = ends[0] if ends else len(lines) - 1
    return lines[:start], lines[start : end + 1], lines[end + 1 :]


def agents_block() -> str:
    """The snippet wrapped in ``# gitwhy-managed`` markers, with a trailing newline."""
    body = agents_template_text().strip("\n")
    return f"{BEGIN_MARKER}\n{body}\n{END_MARKER}\n"


def install_skill_tree(src: Path, dest: Path) -> SkillCopy:
    """Copy ``src`` onto ``dest``. A second copy with the same bytes changes nothing.

    A ``.gitwhy-managed`` sidecar marks the directory. Files the user added beside the
    skill are left in place.
    """
    existed = dest.exists()
    changed = not existed
    for rel in _skill_files(src):
        target = dest / rel
        source = src / rel
        data = source.read_bytes()
        mode = source.stat().st_mode & 0o777
        same_bytes = target.is_file() and target.read_bytes() == data
        same_mode = target.is_file() and (target.stat().st_mode & 0o777) == mode
        if same_bytes and same_mode:
            continue
        changed = True
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(mode)
    marker = dest / MARKER_FILENAME
    marker_text = f"{BEGIN_MARKER}\n"
    if not marker.is_file() or marker.read_text(encoding="utf-8") != marker_text:
        dest.mkdir(parents=True, exist_ok=True)
        marker.write_text(marker_text, encoding="utf-8", newline="\n")
        changed = True
    if not existed:
        return SkillCopy(dest, CopyStatus.CREATED)
    return SkillCopy(dest, CopyStatus.UPDATED if changed else CopyStatus.UNCHANGED)


def install_project_skills(root: Path) -> list[SkillCopy]:
    """Copy the skill into the three project paths."""
    src = bundled_skill_dir()
    return [install_skill_tree(src, root / rel) for rel in PROJECT_SKILL_DIRS]


def install_user_skill() -> SkillCopy:
    """Copy the skill to ``~/.claude/skills/gitwhy``."""
    return install_skill_tree(bundled_skill_dir(), user_skill_dir())


def install_agents_file(root: Path) -> tuple[Path, CopyStatus]:
    """Append the snippet to ``AGENTS.md``, or refresh the managed block already there."""
    path = root / AGENTS_FILENAME
    block = agents_block().splitlines()
    try:
        current = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        path.write_text("\n".join(block) + "\n", encoding="utf-8", newline="\n")
        return path, CopyStatus.CREATED
    if not current.strip():
        updated = "\n".join(block) + "\n"
    else:
        parts = _split_managed(current)
        if parts is None:
            body = current.rstrip("\n")
            updated = f"{body}\n\n" + "\n".join(block) + "\n"
        else:
            before, _, after = parts
            updated = "\n".join([*before, *block, *after]).rstrip("\n") + "\n"
    if updated == current:
        return path, CopyStatus.UNCHANGED
    path.write_text(updated, encoding="utf-8", newline="\n")
    return path, CopyStatus.UPDATED


def uninstall_skill_tree(dest: Path, src: Path) -> bool:
    """Remove a skill copy marked as ours. User files in that directory stay.

    Returns True when a managed copy was found.
    """
    marker = dest / MARKER_FILENAME
    if not marker.is_file():
        return False
    for rel in _skill_files(src):
        target = dest / rel
        if target.is_file():
            target.unlink()
    marker.unlink(missing_ok=True)
    for directory in sorted((path for path in dest.rglob("*") if path.is_dir()), reverse=True):
        if not any(directory.iterdir()):
            directory.rmdir()
    if dest.is_dir() and not any(dest.iterdir()):
        dest.rmdir()
    return True


def uninstall_project_skills(root: Path) -> list[Path]:
    """Remove managed project skill copies. Returns the directories that were managed."""
    src = bundled_skill_dir()
    return [root / rel for rel in PROJECT_SKILL_DIRS if uninstall_skill_tree(root / rel, src)]


def uninstall_user_skill() -> Path | None:
    """Remove the managed user-level Claude skill, if this gitwhy installed it."""
    dest = user_skill_dir()
    if uninstall_skill_tree(dest, bundled_skill_dir()):
        return dest
    return None


def uninstall_agents_file(root: Path) -> tuple[Path, RemoveStatus]:
    """Remove the managed block from ``AGENTS.md``. Other lines stay."""
    path = root / AGENTS_FILENAME
    try:
        current = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return path, RemoveStatus.NOT_INSTALLED
    parts = _split_managed(current)
    if parts is None:
        return path, RemoveStatus.NOT_INSTALLED
    before, _, after = parts
    remaining = [*before, *after]
    if not any(line.strip() for line in remaining):
        path.unlink()
        return path, RemoveStatus.REMOVED_FILE
    path.write_text("\n".join(remaining).rstrip("\n") + "\n", encoding="utf-8", newline="\n")
    return path, RemoveStatus.REMOVED_BLOCK


def mcp_text() -> str:
    """The MCP snippet plus where each agent reads it."""
    return f"{MCP_SNIPPET}\n{MCP_WHERE}"
