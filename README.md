# Whyline

Git-native intent ledger. Capture why a change exists, and get it back when you review, debug, or hand the repo to an agent.

Code is cheap to write. Understanding it is not. The reason for a change dies in a chat or a head, reviewers reverse-engineer a clean diff, and the next session invents a history that was never true. Whyline stores a small structured record next to the code, links it to the commit with a `Whyline-Id` trailer, and returns it at a file and line.

**Status:** specification complete, implementation in progress via the project board.

## Principles

- No invented why. Empty fields stay empty. Agents draft; humans affirm.
- Local-first. No account, no server, no API key on the core path.
- Git is the bus. Records are YAML in `.whyline/records/`. The link is a commit trailer.
- Small records. A screen, not an essay.

## Docs

| Doc | What it is |
|---|---|
| [CLAUDE.md](CLAUDE.md) | Operating manual for the coding agent |
| [docs/00-handoff.md](docs/00-handoff.md) | How to start Claude Code on this package |
| [docs/01-product-spec.md](docs/01-product-spec.md) | Problem, users, scope, metrics |
| [docs/02-architecture.md](docs/02-architecture.md) | Components, flows, trade-offs |
| [docs/03-schema-cli-hooks.md](docs/03-schema-cli-hooks.md) | Schema, CLI, hooks, exit codes |
| [docs/04-roadmap.md](docs/04-roadmap.md) | Phases and issue catalog |
| [docs/05-quality.md](docs/05-quality.md) | Tests, CI, security, release bar |
| [docs/06-github-protocol.md](docs/06-github-protocol.md) | Repo, board, catch-up, next-action rules |
| [docs/07-agent-integrations.md](docs/07-agent-integrations.md) | Skill, MCP, hooks, AGENTS.md — how any coding agent uses Whyline |
| [docs/adapters/claude-code.md](docs/adapters/claude-code.md) | Claude Code skill, MCP, and Stop hook |
| [docs/adapters/other-agents.md](docs/adapters/other-agents.md) | Codex, Cursor, Copilot, and the shell fallback |

## Use from a coding agent

An agent recalls a reason, captures a draft, and checks that a large change has a record. It does not affirm. It does not invent `rejected`, `assumptions`, or `falsifier`.

```sh
whyline why path/to/file.py:88
whyline capture --goal "the user's goal" --file path/to/file.py --pending
whyline check
```

`whyline install-agent` copies one skill into the project and appends the managed block to `AGENTS.md`. If whyline is not on PATH, `skills/whyline/scripts/why.sh` exits 0 and prints `No record: whyline is not on PATH.` `skills/whyline/scripts/capture.sh` exits 127.

MCP is optional, local, and stdio-only. Install it with `uv tool install 'whyline[mcp]'`. The server does not affirm.

```json
{
  "mcpServers": {
    "whyline": {
      "command": "whyline-mcp"
    }
  }
}
```

Where that JSON goes: [Claude Code](docs/adapters/claude-code.md) and [Codex, Cursor, Copilot, and other agents](docs/adapters/other-agents.md).

## License

Apache License 2.0. See [LICENSE](LICENSE).
