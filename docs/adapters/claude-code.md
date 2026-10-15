# Claude Code

Claude Code uses the same skill text as every other agent, plus a Stop hook that may draft a record. The hook never affirms.

## Install the skill

From the repository Claude Code is editing:

```sh
intentline install-agent
```

That copies the skill to `.claude/skills/intentline` and `.agents/skills/intentline`, updates `AGENTS.md`, and prints the MCP snippet.

To also install the skill for every project on this machine:

```sh
intentline install-agent --claude
```

The user-level copy is `~/.claude/skills/intentline`.

Do not rewrite the skill. The text lives once, in the Intentline package. A second `install-agent` refreshes the copy.

## MCP

Install the extra, then register the server:

```sh
uv tool install 'intentline[mcp]'
claude mcp add --scope project intentline -- intentline-mcp
```

Project scope writes `.mcp.json`. User scope is:

```sh
claude mcp add --scope user intentline -- intentline-mcp
```

That updates `~/.claude.json`.

Or paste this into `.mcp.json` yourself. Intentline does not write that file.

```json
{
  "mcpServers": {
    "intentline": {
      "command": "intentline-mcp"
    }
  }
}
```

The server does not affirm.

## Stop hook

The Stop hook reads the session, and when the session touched files (or something is staged) and `.intentline/pending` is empty, it writes one draft. It uses only what the session actually contains. It does not invent rejected alternatives, assumptions, or a falsifier.

Print the hook snippet:

```sh
intentline adapters claude
```

Write it into `.claude/settings.json` without changing other keys:

```sh
intentline adapters claude --write
```

The command Claude Code runs exits 0 when Intentline is missing:

```text
intentline is not on PATH
```

A missing session file also exits 0. The hook never affirms, and it never blocks the turn.

`templates/claude-plugin/` is a hook-only plugin. It does not contain a second copy of the skill. Install the skill with `intentline install-agent`.

## What the agent may do

```sh
intentline why path/to/file.py:88
intentline capture --goal "the user's goal" --file path/to/file.py --pending
intentline check
```

If Intentline is not on PATH, `skills/intentline/scripts/why.sh` exits 0 and prints `No record: intentline is not on PATH.` `scripts/capture.sh` exits 127.

The agent does not run `intentline affirm`.
