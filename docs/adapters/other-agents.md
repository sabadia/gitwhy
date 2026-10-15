# Other agents

Codex, Cursor, Copilot, Gemini, Aider, and OpenCode use the same skill and the same MCP server. There is no per-agent hook. Do not rewrite the skill.

## Shared commands

```sh
intentline why path/to/file.py:88
intentline capture --goal "the user's goal" --file path/to/file.py --pending
intentline check
```

```sh
intentline install-agent
```

That copies one skill into `.agents/skills/intentline`, `.claude/skills/intentline`, and `.github/skills/intentline`.

If Intentline is not on PATH, `skills/intentline/scripts/why.sh` exits 0 and prints:

```text
No record: intentline is not on PATH.
```

`skills/intentline/scripts/capture.sh` exits 127. The server does not affirm.

## MCP snippet

Install `uv tool install 'intentline[mcp]'` first. The command is `intentline-mcp`.

```json
{
  "mcpServers": {
    "intentline": {
      "command": "intentline-mcp"
    }
  }
}
```

## Codex

```sh
codex mcp add intentline -- intentline-mcp
```

That writes `~/.codex/config.toml`. For a trusted project, the same block can live in `.codex/config.toml`:

```toml
[mcp_servers.intentline]
command = "intentline-mcp"
```

The skill directory Codex reads is `.agents/skills/intentline`.

## Cursor

Put the JSON in `.cursor/mcp.json` in the project, or in `~/.cursor/mcp.json`. Cursor needs `"type": "stdio"` on that server entry:

```json
{
  "mcpServers": {
    "intentline": {
      "type": "stdio",
      "command": "intentline-mcp"
    }
  }
}
```

Cursor skills can also live in `.cursor/skills`. Intentline's install copies the canonical skill to `.agents/skills` and `.claude/skills`. Point Cursor at one of those, or copy that same directory. Do not fork the text.

## GitHub Copilot

```sh
copilot mcp add intentline -- intentline-mcp
```

The project MCP file is `.github/mcp.json`. The skill directory Copilot reads from this install is `.github/skills/intentline`.

## Gemini, Aider, and OpenCode

Use the shell commands above, the skill at `.agents/skills/intentline`, and the shared MCP JSON. They do not get a separate hook.

## What an agent must not do

- Affirm a record.
- Invent `rejected`, `assumptions`, or `falsifier`.
- Rewrite the skill into an agent-specific copy.
