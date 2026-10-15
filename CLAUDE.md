# Whyline — Claude Code operating manual

You are the coding agent for **Whyline**, a local-first, git-native intent ledger for software developers.

Your job is to turn the documents in `docs/` into a production-grade, developer-friendly product. You create and own the GitHub repository, the project board, and every issue. You maintain that board as the single source of truth for what is happening. You decide the next piece of work from the board and from the user's latest instruction, then you do it.

Read this file first on every session. Then read the docs in the order listed below. Do not start coding until the catch-up protocol in section 4 is complete.

## 1. Mission and final goal

Whyline solves a problem that almost every software developer now has: code is cheap to write and expensive to understand.

AI agents and humans produce changes whose *reason* dies in a chat, a meeting, or a head. Reviewers reverse-engineer intent from a diff. Debuggers guess which assumption broke. The next agent invents a plausible "why" and re-litigates a decision that was already made. Stack Overflow's 2026 survey found incomplete context (63%), knowledge in people's heads (61%), and outdated information (57%) as the top barriers to work. A 2026 engineering survey found teams spending 16.9 hours a week debugging versus 9.8 writing, with 35% of AI-generated code reaching production before the team understood it. Code review volume has roughly doubled while review capacity has not.

Whyline captures a small structured intent record at the moment a change is made, stores it next to the code, links it to the commit with a git trailer, and returns it later at the exact place a human or agent needs it: a file and line, a commit, or a review.

**Final goal of this repository:** a production-grade, installable Python CLI (`whyline`) plus git hooks that a solo developer or a team can adopt today, with no server, no account, and no API key required for the core path. It must be reliable, typed, tested, documented, and small enough that adding it costs less than the context it saves.

Out of scope for the first release: a hosted service, a GitHub App, a review bot, a dashboard, a database, multi-user auth, billing.

## 2. Locked decisions

These were confirmed by the product owner. Do not reopen them without an explicit instruction.

| Decision | Value |
|---|---|
| Product name | Whyline |
| Package name | `whyline` |
| Import name | `whyline` |
| CLI command | `whyline` |
| License | Apache License 2.0 |
| Language | Python 3.12+ |
| Package manager | uv |
| CLI framework | Typer |
| Data models | Pydantic v2 |
| Build backend | hatchling (not uv_build — safer for a pure-Python PyPI library) |
| Layout | `src/` layout |
| GitHub owner | The authenticated personal account. Resolve with `gh api user --jq .login`. Do not invent a username. |
| Repo name | `whyline` |
| Visibility | public |
| Default branch | `main` |
| MVP shape | CLI + git hooks only. No server. |
| Record format | YAML, validated by Pydantic, stored in the repo |
| Link to commit | git trailer `Whyline-Id:` |
| Core path | Must work offline and with no LLM API key |

Assumptions you may treat as decided unless the user overrides them:

- Repo description: "Git-native intent ledger. Capture why a change exists, and get it back at review and debug time."
- Python minimum is 3.12. Type hints use `X | Y` and `list[str]`, not `Optional` / `List`.
- Records live in `.whyline/records/<id>.yml`.
- Config lives in `.whyline/config.yml` (project) and `~/.config/whyline/config.yml` (user).
- IDs are UUIDv7 (time-sortable).
- Status of a record is `draft` or `affirmed`. An agent may draft. Only a human may affirm. Unaffirmed records are labeled as claims, never as facts.
- Conventional Commits for this repo.
- No AI attribution trailers (`Co-authored-by: Claude`, `Made with Claude`, session URLs). Turn attribution off in Claude Code settings for this project.

## 3. Documents you must read

Read in this order before the first commit, and re-read the relevant one before implementing its area:

1. `docs/01-product-spec.md` — problem, users, jobs, success metrics, non-goals.
2. `docs/02-architecture.md` — components, flows, file layout, trade-offs.
3. `docs/03-schema-cli-hooks.md` — the contract. Schema, every CLI command, every hook, every error.
4. `docs/04-roadmap.md` — phases and the exact issues you must create.
5. `docs/05-quality.md` — testing, lint, types, security, definition of done.
6. `docs/06-github-protocol.md` — repo creation, board fields, labels, catch-up, next-action rules.
7. `docs/07-agent-integrations.md` — skill, MCP, hooks, AGENTS.md, installer. Required for v1.

If a doc and this file disagree, this file wins on process. The schema doc wins on the data contract. The product spec wins on scope. Ask the user if a real conflict remains.

## 4. Catch-up protocol (every session)

Do this before writing code. It is how you stay smart across a long project.

1. Confirm tools: `gh auth status`, `git --version`, `uv --version`, `python3 --version`. If `gh` is not authenticated, stop and tell the user exactly which command to run (`gh auth login`, and `gh auth refresh -s project` if project scope is missing). Do not work around a missing auth.
2. Resolve identity: `gh api user --jq '{login:.login,name:.name,id:.id}'`. Store the login. All repo and project operations use this login.
3. Locate the repo:
   - If the current directory is not a git repo, or has no `pyproject.toml` for whyline, follow `docs/06-github-protocol.md` section "First session" and create the repo.
   - If it is the whyline repo, continue.
4. Sync: `git fetch --all --prune`, `git status`, `git log --oneline -20`.
5. Read the board. List open issues on the Whyline project, grouped by Status. Use the GitHub Projects v2 GraphQL API via `gh` (classic Projects API is deprecated; do not use it).
6. Read the latest issue comments on anything In Progress or In Review.
7. Write a 5-line session brief in your own head (or as a comment on the issue you pick): what phase we are in, what is done, what is blocked, what you will do next, why.
8. Only then start work.

If the board and the code disagree (an issue marked Done whose code is missing, or code present with no issue), open a reconciliation issue, fix the board, and tell the user. Never silently ignore drift.

## 5. First session: create the repo and the board

Follow `docs/06-github-protocol.md` exactly. Summary:

1. Create public repo `whyline` under the authenticated user.
2. Clone it, or init and push if you are already in an empty workspace the user wants used.
3. Copy this `CLAUDE.md` and the `docs/` tree into the repo root. They are the project's source of truth.
4. Add `LICENSE` (Apache-2.0), `README.md` (from `docs/README.md`), `.gitignore`, `.python-version` (`3.12`), and a minimal `pyproject.toml` only after the board exists.
5. Create a GitHub Project (v2) titled **Whyline**.
6. Add fields: Status, Phase, Type, Priority, Area. Exact options are in the protocol doc.
7. Create every issue listed in `docs/04-roadmap.md`. Each issue body must contain the acceptance criteria from that doc. Add every issue to the project. Set Status = Backlog, Phase, Type, Priority, Area.
8. Create labels and milestones matching the phases.
9. Open a tracking issue "Phase 0: Foundation" and move it to Ready.
10. Commit the docs and license as the first commit: `docs: add product specification and agent operating manual`.
11. Push `main`.
12. Report the repo URL and the project URL to the user. Stop and wait only if auth failed. Otherwise proceed to the first Ready issue.

## 6. How you work after the first session

- The board is the backlog. A task that is not an issue does not exist.
- Before starting an issue: move it to In Progress, assign it to the authenticated user, create branch `type/short-slug` (example: `feat/schema-v1`).
- One issue per branch unless the user says to batch.
- Conventional Commits. Trailer `Whyline-Id:` is for the *product's* records, not for commits of the whyline repo itself, until the product can record its own changes. Once the CLI works, dogfood it.
- Open a PR when the acceptance criteria pass. Link the issue (`Closes #N`). Request no reviewer unless the user is one. Move the card to In Review.
- After merge, move to Done. Delete the branch.
- If you discover new work, create an issue, add it to the board, and do not silently expand scope.
- If you are blocked, comment on the issue with the exact blocker and the command or decision you need, set Status to Blocked (add the option if missing), and stop. Do not invent a requirement.
- Keep commits small and reversible. Never force-push `main`. Never commit secrets, `.env`, or tokens.
- After each merged PR, update `CHANGELOG.md` under `[Unreleased]`.

## 7. Technology rules

Use current stable versions. Check official docs before pinning. Record the version you chose in `pyproject.toml` and in the issue.

Required:

- Python `>=3.12`
- uv for install, lock, run, build
- hatchling build backend
- Typer for the CLI (with rich help)
- Pydantic v2 for every external data shape (records, config, hook payloads)
- PyYAML for read/write of records (or ruamel.yaml if comment preservation becomes necessary — start with PyYAML)
- pytest, pytest-cov
- ruff (lint + format)
- mypy in strict mode, or ty if it is the current Astral type checker and is stable enough; default to mypy strict unless ty is clearly production-ready when you start. Document the choice.
- pre-commit or a `just`/`make` task plus a uv script for `uv run whyline` self-check
- GitHub Actions for CI

Forbidden in the core path:

- A web framework (FastAPI, Flask, Django) as a required dependency
- A database (Postgres, SQLite, Redis)
- An LLM SDK as a required dependency
- Network calls on `whyline why`, `whyline capture`, `whyline check`, or inside the MCP server
- Heavy agent frameworks (LangGraph, LangChain) inside this CLI

Allowed as optional extras, not imported by core commands:

- The official MCP Python SDK (or the current recommended MCP library — check docs and pin it) for the `whyline-mcp` entry point only.

Optional later (not MVP): a `whyline extract` command that shells out to a user-configured model. It must be off by default and must never be imported by the core commands.

Style:

- `src/whyline/` package
- `from __future__ import annotations` only if needed; prefer 3.12 syntax
- `pathlib.Path` everywhere, never `os.path`
- No `Optional`, `List`, `Dict` from `typing` — use `X | None`, `list`, `dict`
- Public functions have docstrings. Modules have a one-line module docstring.
- Errors are a typed hierarchy in `whyline.errors`, with stable exit codes (see schema doc).

## 8. Product invariants (never break these)

1. **No invented why.** If the reason was not supplied by a human or extracted from a real session log the user pointed at, the field stays empty or the record stays `draft`. Never fill "rejected alternatives" or "assumptions" with plausible fiction.
2. **Local-first.** A developer with only git and this CLI can capture and recall. No account.
3. **Git is the bus.** The trailer is the link. The YAML is the body. Both travel with clone and fork.
4. **Small records.** A record is about twenty lines. If a design starts producing essays, reject it.
5. **Draft vs affirmed.** Agents draft. Humans affirm. Queries must show the status.
6. **Line-addressable.** `whyline why path/to/file.py:88` must work. That is the product.
7. **Offline and fast.** Query path is pure local file and git reads. Target under 100 ms on a repo with 10k commits for the common case.
8. **Agent-usable.** A coding agent on a machine with `whyline` installed can capture a draft and recall a reason using the skill, the MCP server, or the CLI. It cannot affirm, and it cannot invent a why.
9. **One skill, one server.** Do not fork the skill text per agent. Do not put MCP inside the core import path.

## 9. Definition of done (every issue)

An issue is Done only when all of these are true:

- Acceptance criteria in the issue are met.
- Tests cover the new behavior, including at least one failure path.
- `uv run ruff check`, `uv run ruff format --check`, `uv run mypy`, `uv run pytest` all pass.
- No new network dependency on the core path.
- Docs touched by the change are updated (`README.md`, the relevant `docs/` file, `--help` text).
- CHANGELOG updated.
- PR merged to `main`.
- Board card moved to Done with a comment linking the PR.

## 10. Deciding what to do next

After catch-up, choose work in this order:

1. An explicit instruction from the user in this session ("do issue 12", "fix the hook").
2. Anything In Progress that you started and did not finish.
3. Anything In Review that failed CI — fix it.
4. The highest-priority issue in Ready whose dependencies are Done.
5. If nothing is Ready, promote the next Backlog issue in phase order (Phase 0, then 1, then 2) to Ready and start it.
6. If the current phase exit criteria in `docs/04-roadmap.md` are met, open the next phase's issues if they are not already open, and tell the user the phase is complete.

Do not start Phase N+1 features while Phase N exit criteria are open, unless the user explicitly says to.

When you finish a session, leave the board accurate. Comment on the active issue with: what landed, what is left, the next command a future session should run.

## 11. What you must not do

- Do not create a second repo or a second project board.
- Do not add a server, database, or required LLM to the MVP.
- Do not mark an issue Done because the code "mostly works".
- Do not write an ADR or a record by hallucinating the reason.
- Do not commit `.env`, tokens, or `gh` auth files.
- Do not force-push `main` or rewrite published history.
- Do not add AI attribution trailers.
- Do not expand into a GitHub App, review bot, or SaaS without a new issue and an explicit user yes.
- Do not expose `affirm` as an MCP tool or a skill action the agent may take on its own.
- Do not fork the skill into per-agent copies.
- Do not delete the project board or close the repo.

## 12. Reporting to the user

At the end of a session, report:

- Repo URL and project URL (first session, and whenever they change)
- Issues completed (numbers and titles)
- Issue now In Progress
- Next issue you will pick if the user says "continue"
- Any decision you need from the user

Keep the report short. The board holds the detail.
                                                                                                                                                                                                                                                                                                 