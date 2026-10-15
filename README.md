# Whyline

Git-native intent ledger. Capture why a change exists, and get it back when you review, debug, or hand the repo to an agent.

Code is cheap to write. Understanding it is not.
The reason for a change dies in a chat or a head.
Reviewers reverse-engineer a clean diff, and the next session invents a history that was never true.
Whyline stores a small structured record next to the code, links it to the commit with a `Whyline-Id` trailer, and returns it at a file and line.

**Status:** pre-release, MVP in progress.

## Install

Whyline is not on PyPI yet. Install it from git:

```sh
uv tool install git+https://github.com/sabadia/whyline
```

After it is published:

```sh
uv tool install whyline
```

The optional MCP extra is `uv tool install 'whyline[mcp]'`. Core commands need no account and no API key.

## Quickstart

```sh
cd your-repo
whyline init
whyline install-hooks
git add src/app.py
whyline capture --goal "Close invoices once a day."
whyline link <id>
git add .whyline
git commit -m "feat: close invoices once a day"
whyline why src/app.py:1
```

`whyline capture --pending` is the same mark as `whyline link <id>`. If you abort the commit after the hook runs, that mark is already gone; run `whyline link <id>` again.

## Principles

- No invented why. Empty fields stay empty. Agents draft; humans affirm.
- Local-first. No account, no server, no API key on the core path.
- Git is the bus. Records are YAML in `.whyline/records/`. The link is a commit trailer.
- Small records. A screen, not an essay.

The product spec is [docs/01-product-spec.md](docs/01-product-spec.md).

## Limits

- `--amend-head` treats a commit as pushed when any of this clone's remote-tracking refs contain it. That check does not contact the network. On a detached HEAD, capture and link still work; `--amend-head` refuses.
- A shallow clone may miss older records. `whyline why` says so.
- Whyline uses the repository you are in. Inside a submodule, that is the submodule, not the parent.
- On a deleted path, `why` may find nothing. `whyline show <id>` still prints the record.
- In an empty repository, init and capture work. `why` says there are no commits yet and exits 0.
- Two captures at once: the last write wins, and the ids do not collide.
- Records are committed with the code. Do not put secrets in goals. Whyline does not scan for them.

## Exit codes

`whyline --help` lists them, from 0 ok through 9 not found. The contract is [docs/03-schema-cli-hooks.md](docs/03-schema-cli-hooks.md).

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
