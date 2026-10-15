# Other agents

One skill, one MCP server, one CLI. Do not keep a second copy of the skill text. `gitwhy install-agent` writes that skill to `.agents/skills/gitwhy`, `.claude/skills/gitwhy`, and `.github/skills/gitwhy`, and appends a managed block to `AGENTS.md`.

An agent drafts. It does not affirm. It does not invent `rejected`, `assumptions`, or `falsifier`.

If gitwhy is not on PATH, `skills/gitwhy/scripts/why.sh` exits 0 and prints `No record: gitwhy is not on PATH.` `skills/gitwhy/scripts/capture.sh` exits 127. That is a missing tool. It is not a reason to write a record by hand.

The three commands:

```sh
gitwhy why path/to/file.py:88
gitwhy capture --goal "the user's goal" --file path/to/file.py --pending
gitwhy check
```

Capture writes `.gitwhy/records/` and, with `--pending`, `.gitwhy/pending`. Commit the record with `git add .gitwhy`. MCP needs `uv tool install 'gitwhy[mcp]'`. The server is local stdio and has no affirm tool. `gitwhy install-agent --mcp` prints the JSON. Gitwhy does not write the agent's config file.

## Codex

Codex reads `AGENTS.md` and skills under `.agents/skills` from the working directory up to the repository root. The user copy is `~/.agents/skills`. `gitwhy install-agent` writes the repo skill and the `AGENTS.md` block. [Codex skills](https://developers.openai.com/codex/skills).

MCP is `config.toml`. `codex mcp add gitwhy -- gitwhy-mcp` writes the user file `~/.codex/config.toml`. A trusted project can use `.codex/config.toml` instead:

```toml
[mcp_servers.gitwhy]
command = "gitwhy-mcp"
```

[Codex MCP](https://developers.openai.com/codex/mcp). There is no gitwhy hook for Codex.

## Cursor

Project MCP is `.cursor/mcp.json`. User MCP is `~/.cursor/mcp.json`. Both use the `mcpServers` object `gitwhy install-agent --mcp` prints. Cursor's stdio table requires `"type": "stdio"` on that server. [Cursor MCP](https://cursor.com/docs/mcp).

Cursor loads skills from `.cursor/skills/<name>/SKILL.md`. [Cursor skills](https://cursor.com/docs/skills). `gitwhy install-agent` does not write that directory. Copy `.agents/skills/gitwhy` to `.cursor/skills/gitwhy` when you want Cursor to load it. Copy the directory. Do not rewrite the skill.

There is no gitwhy hook for Cursor.

## Copilot

Copilot reads project skills from `.github/skills`, `.claude/skills`, or `.agents/skills`, and personal skills from `~/.copilot/skills` or `~/.agents/skills`. `gitwhy install-agent` writes the three project copies. [About agent skills](https://docs.github.com/en/copilot/concepts/agents/about-agent-skills).

Copilot CLI stores user MCP servers in `~/.copilot/mcp-config.json`:

```sh
copilot mcp add gitwhy -- gitwhy-mcp
```

For one repository, commit `.mcp.json` or `.github/mcp.json` with the same `mcpServers` object and `"type": "stdio"`. [Add MCP servers for Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers). There is no gitwhy hook for Copilot.

## Gemini CLI, Aider, OpenCode, and any other agent

Run the three commands above. If the agent reads Agent Skills, point it at `.agents/skills/gitwhy`. If it speaks MCP, give it the JSON from `gitwhy install-agent --mcp` (`command` is `gitwhy-mcp`, transport is stdio). There is no per-agent hook and no second skill file.
