# Gitwhy

Git-native intent ledger. Capture why a change exists, and get it back when you review, debug, or hand the repo to an agent.

Code is cheap to write. Understanding it is not. The reason for a change dies in a chat or a head, reviewers reverse-engineer a clean diff, and the next session invents a history that was never true. Gitwhy stores a small structured record next to the code, links it to the commit, and returns it at a file and line.

**Status:** specification complete, implementation not started. This repository is the product.

## Principles

- No invented why. Empty fields stay empty. Agents draft; humans affirm.
- Local-first. No account, no server, no API key on the core path.
- Git is the bus. The record is YAML in `.gitwhy/records`. The link is a `Gitwhy-Id` trailer.
- Small records. A screen, not an essay.

## Docs

Start here if you are implementing this:

| Doc | What it is |
|---|---|
| [CLAUDE.md](../CLAUDE.md) | Operating manual for the coding agent |
| [docs/01-product-spec.md](01-product-spec.md) | Problem, users, scope, metrics |
| [docs/02-architecture.md](02-architecture.md) | Components, flows, trade-offs |
| [docs/03-schema-cli-hooks.md](03-schema-cli-hooks.md) | The contract: schema, CLI, hooks, errors |
| [docs/04-roadmap.md](04-roadmap.md) | Phases and the issue catalog |
| [docs/05-quality.md](05-quality.md) | Tests, CI, security, release bar |
| [docs/06-github-protocol.md](06-github-protocol.md) | Repo, board, catch-up, next-action rules |
| [docs/07-agent-integrations.md](07-agent-integrations.md) | Skill, MCP, hooks, AGENTS.md |

## License

Apache License 2.0. See [LICENSE](../LICENSE).
