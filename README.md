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

## License

Apache License 2.0. See [LICENSE](LICENSE).
