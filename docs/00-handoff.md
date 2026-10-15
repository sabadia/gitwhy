# Hand this to Claude Code

## What this package is

A complete, implementation-ready specification for **Gitwhy**: a local-first CLI that records why a code change exists and returns that reason at review and debug time.

Locked choices:

- Name: Gitwhy
- License: Apache-2.0
- Stack: Python 3.12+, uv, Typer, Pydantic v2, hatchling
- MVP: CLI + git hooks + agent surfaces (portable skill, local MCP server, AGENTS.md snippet)
- GitHub: a new public repo `gitwhy` under your personal account (Claude Code resolves the username from `gh`)

Any coding agent must be able to use the finished tool. That is a v1 requirement, specified in `docs/07-agent-integrations.md`.

## How to use it

1. Install and authenticate the GitHub CLI (`gh auth login`). Refresh project scope if needed: `gh auth refresh -s project`.
2. Create an empty folder, or open the folder where you want the repo.
3. Copy this entire package into that folder so `CLAUDE.md` is at the root and `docs/` sits beside it.
4. Open the folder in Claude Code and paste the prompt below as the first message.

Claude Code will create the GitHub repo, the project board, every issue, and then start Phase 0. The board is the memory. Later sessions start by reading the board and continuing.

## First prompt (paste this)

```
Read CLAUDE.md and every file in docs/ before you write code.

You are the coding agent for Gitwhy. Follow CLAUDE.md exactly.

Do this now:
1. Run the catch-up / first-session protocol in CLAUDE.md and docs/06-github-protocol.md.
2. Resolve my GitHub login with `gh api user --jq .login`. Use that as the owner. Do not guess.
3. Create the public repo `gitwhy` if it does not exist, with the Apache-2.0 license.
4. Commit this CLAUDE.md, docs/, README, and LICENSE, and push main.
5. Create the GitHub Project v2 board "Gitwhy" with the fields in docs/06-github-protocol.md.
6. Create every issue in docs/04-roadmap.md, add each to the board, and set Status, Phase, Type, Priority, and Area.
7. Use current official docs for uv, hatchling, Typer, Pydantic v2, gh project, git trailers, Agent Skills (agentskills.io), and the MCP Python SDK. Do not rely on stale memory.
8. Agent surfaces are required for v1, not optional. Follow docs/07-agent-integrations.md. Ship one portable skill, a local stdio MCP server as an optional extra, an AGENTS.md snippet, and install-agent. Do not expose affirm to agents. Do not fork the skill per agent.
9. When the board exists, start issue 0.2 (uv project and tooling) unless 0.1 is still open. Mark 0.1 Done once the repo, board, and issues exist.
10. Keep the board accurate after every task. One issue per branch. Conventional Commits. No AI attribution trailers.
11. At the end, give me the repo URL, the project URL, and the next issue you will do if I say "continue".

If gh is not authenticated, stop and tell me the exact command. Do not work around it.
If a spec is ambiguous, prefer CLAUDE.md on process, docs/03 on the data contract, and docs/01 on scope. Ask me only if those still conflict.
```

## Later sessions

Paste:

```
Read CLAUDE.md. Run the catch-up protocol. Continue Gitwhy from the board. Take the next Ready issue, or resume In Progress. Do not ask what to do next unless you are blocked. Report the repo, what you finished, and what you will do if I say continue.
```

## What you still need to do once

- `gh auth login` on the machine where Claude Code runs.
- Say "continue" when you want the next issue, or name an issue.
- Say yes before any PyPI publish or version tag. The spec already tells Claude Code to ask.
