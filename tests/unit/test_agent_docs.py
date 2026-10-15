"""Per-agent docs stay aligned with the skill, the MCP snippet, and the missing-CLI failure."""

from pathlib import Path

from gitwhy.adapters.skill import MCP_SNIPPET

ROOT = Path(__file__).resolve().parents[2]
README = (ROOT / "README.md").read_text(encoding="utf-8")
CLAUDE = (ROOT / "docs" / "adapters" / "claude-code.md").read_text(encoding="utf-8")
OTHERS = (ROOT / "docs" / "adapters" / "other-agents.md").read_text(encoding="utf-8")

_WHY_MISSING = "No record: gitwhy is not on PATH."
_COMMANDS = (
    "gitwhy why path/to/file.py:88",
    'gitwhy capture --goal "the user\'s goal" --file path/to/file.py --pending',
    "gitwhy check",
)


def test_readme_tells_an_agent_the_three_commands_and_the_mcp_snippet() -> None:
    assert "## Use from a coding agent" in README
    for command in _COMMANDS:
        assert command in README
    assert MCP_SNIPPET.strip() in README
    assert "does not affirm" in README
    assert _WHY_MISSING in README
    assert "exits 127" in README


def test_claude_code_doc_installs_skill_mcp_and_hook_and_never_affirms() -> None:
    assert "gitwhy install-agent" in CLAUDE
    assert "claude mcp add --scope project gitwhy -- gitwhy-mcp" in CLAUDE
    assert "gitwhy adapters claude --write" in CLAUDE
    assert "never affirms" in CLAUDE
    assert "gitwhy is not on PATH" in CLAUDE
    assert "templates/claude-plugin/" in CLAUDE
    assert not (ROOT / "templates" / "claude-plugin" / "skills").exists()


def test_other_agents_names_each_config_and_the_missing_cli_failure() -> None:
    assert _WHY_MISSING in OTHERS
    assert "exits 127" in OTHERS
    assert "does not affirm" in OTHERS
    for command in _COMMANDS:
        assert command in OTHERS
    assert "codex mcp add gitwhy -- gitwhy-mcp" in OTHERS
    assert "~/.codex/config.toml" in OTHERS
    assert ".codex/config.toml" in OTHERS
    assert ".cursor/mcp.json" in OTHERS
    assert "~/.cursor/mcp.json" in OTHERS
    assert '"type": "stdio"' in OTHERS
    assert ".cursor/skills" in OTHERS
    assert ".github/skills" in OTHERS
    assert "copilot mcp add gitwhy -- gitwhy-mcp" in OTHERS
    assert ".github/mcp.json" in OTHERS
    assert "Do not rewrite the skill" in OTHERS
