# Intentline

Git-native intent ledger. Capture why a change exists, and get it back when you review, debug, or hand the repo to an agent.

Code is cheap to write. Understanding it is not.
The reason for a change dies in a chat or a head.
Reviewers reverse-engineer a clean diff, and the next session invents a history that was never true.
Intentline stores a small structured record next to the code, links it to the commit with an `Intentline-Id` trailer, and returns it at a file and line.

**Status:** v0.1.0 on PyPI.

## Install

```sh
uv tool install intentline
```

From git:

```sh
uv tool install git+https://github.com/sabadia/intentline
```

The optional MCP extra is `uv tool install 'intentline[mcp]'`. Core commands need no account and no API key.

The manual starts at [docs/getting-started.md](docs/getting-started.md). The full index is [docs/README.md](docs/README.md).

## Quickstart

```sh
cd your-repo
intentline init
intentline install-hooks
git add src/app.py
intentline capture --goal "Close invoices once a day."
intentline link <id>
git add .intentline
git commit -m "feat: close invoices once a day"
intentline why src/app.py:1
```

`intentline capture --pending` is the same mark as `intentline link <id>`. If you abort the commit after the hook runs, that mark is already gone; run `intentline link <id>` again.

## Principles

- No invented why. Empty fields stay empty. Agents draft; humans affirm.
- Local-first. No account, no server, no API key on the core path.
- Git is the bus. Records are YAML in `.intentline/records/`. The link is a commit trailer.
- Small records. A screen, not an essay.

## Limits

- `--amend-head` treats a commit as pushed when any of this clone's remote-tracking refs contain it. That check does not contact the network.
- A shallow clone may miss older records. `intentline why` says so.
- Records are committed with the code. Do not put secrets in goals. Intentline does not scan for them.

The rest, including submodules, deleted paths, and empty repositories: [docs/limits.md](docs/limits.md).

## Exit codes

`intentline --help` lists them, from 0 ok through 9 not found. The table is [docs/exit-codes.md](docs/exit-codes.md).

## Docs

| Guide | What it is |
|---|---|
| [Getting started](docs/getting-started.md) | First record, first recall |
| [Installation](docs/installation.md) | PyPI, git, MCP, upgrade |
| [Records](docs/records.md) | Every field, draft and affirmed |
| [Capture](docs/capture.md) | Flags, prompts, session logs |
| [Linking](docs/linking.md) | The trailer and amend |
| [Recall](docs/recall.md) | `why`, `show`, `list` |
| [Affirm](docs/affirm.md) | A human confirms a reason |
| [Check](docs/check.md) | Large changes need a record |
| [Hooks](docs/hooks.md) | prepare-commit-msg and pre-commit |
| [Configuration](docs/configuration.md) | Project and user config |
| [Coding agents](docs/agents.md) | Skill, MCP, install |
| [Claude Code](docs/adapters/claude-code.md) | Skill, MCP, Stop hook |
| [Other agents](docs/adapters/other-agents.md) | Codex, Cursor, Copilot, shell |
| [Troubleshooting](docs/troubleshooting.md) | Exit codes in practice |
| [Contributing](docs/contributing.md) | Changing this codebase |

## Use from a coding agent

An agent recalls a reason, captures a draft, and checks that a large change has a record. It does not affirm. It does not invent `rejected`, `assumptions`, or `falsifier`.

```sh
intentline why path/to/file.py:88
intentline capture --goal "the user's goal" --file path/to/file.py --pending
intentline check
```

`intentline install-agent` copies one skill into the project and appends the managed block to `AGENTS.md`. If intentline is not on PATH, `skills/intentline/scripts/why.sh` exits 0 and prints `No record: intentline is not on PATH.` `skills/intentline/scripts/capture.sh` exits 127.

MCP is optional, local, and stdio-only. Install it with `uv tool install 'intentline[mcp]'`. The server does not affirm.

```json
{
  "mcpServers": {
    "intentline": {
      "command": "intentline-mcp"
    }
  }
}
```

Where that JSON goes: [Claude Code](docs/adapters/claude-code.md) and [Codex, Cursor, Copilot, and other agents](docs/adapters/other-agents.md).

## License

Apache License 2.0. See [LICENSE](LICENSE).
