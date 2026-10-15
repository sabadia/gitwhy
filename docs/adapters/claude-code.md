# Claude Code

The Stop hook drafts one record when a session ends. It never affirms. The skill is the same file `gitwhy install-agent` copies. This plugin does not carry a second copy.

## Install

1. `gitwhy install-agent` copies the skill to `.claude/skills/gitwhy` and appends the managed block to `AGENTS.md`.
2. `uv tool install 'gitwhy[mcp]'`, then `claude mcp add --scope project gitwhy -- gitwhy-mcp`. The server has no affirm tool.
3. `gitwhy adapters claude --write` merges the Stop hook into this repository's `.claude/settings.json`.

Other agents: [other-agents.md](other-agents.md).

## Stop hook

`gitwhy adapters claude` prints a snippet. `gitwhy adapters claude --write` merges it into `.claude/settings.json` at the repository root. A missing file is created. A second run does not add a second hook and does not rewrite the file. Other keys in that file stay as they are.

The command Claude Code runs:

```text
sh -c 'command -v gitwhy >/dev/null 2>&1 || exit 0; gitwhy adapters claude-stop'
```

Claude Code sends a JSON payload on the hook's stdin. The session file is the `transcript_path` field. That field is on every hook payload ([Hooks](https://code.claude.com/docs/en/hooks)). The directory under `~/.claude/projects` is not a stable path, so gitwhy does not guess it and does not hardcode it.

`gitwhy adapters claude-stop` writes one draft only when all of these are true:

- `transcript_path` names a file that exists
- that file has a user message (that text is the goal)
- the session lists files inside this repository, or something is staged
- `.gitwhy/pending` is empty
- this directory is a git repository and `gitwhy init` has been run

The record is a draft. `author.tool` is `claude-code`. `source.kind` is `session`. Rejected alternatives, assumptions, and the falsifier stay empty. The hook does not affirm.

Anything else exits 0 and writes nothing: gitwhy is not on PATH, the session file is missing, the payload is bad, gitwhy is not initialized, or the command fails. `stop_hook_active: true` (Claude Code sets this when a hook already blocked and the turn is re-entering) also writes nothing, so the hook cannot loop. The hook never prints a `decision: block`.

`--write` exits 2 outside a git repository and exits 4 when `.claude/settings.json` is not a JSON object. Printing the snippet exits 0 anywhere.

## Plugin

`templates/claude-plugin/` is a hook-only plugin. `plugin.json` is the only file under `.claude-plugin/`. `hooks/hooks.json` is the same Stop hook the command prints. There is no `skills/` directory in the plugin.

From a checkout of this repository:

```text
claude --plugin-dir templates/claude-plugin
```

Copy that directory if you want the plugin outside the checkout. Install the skill separately so there is still one skill text:

```text
gitwhy install-agent
```

## MCP

The server is local stdio and optional. It does not include an affirm tool.

```text
uv tool install 'gitwhy[mcp]'
claude mcp add --scope project gitwhy -- gitwhy-mcp
```

User scope is `claude mcp add --scope user gitwhy -- gitwhy-mcp`. The same server can be declared in `.mcp.json` as `gitwhy install-agent` prints it. Gitwhy does not write that file.
