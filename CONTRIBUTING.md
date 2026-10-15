# Contributing to Whyline

Whyline is a local-first CLI. Contributions that keep the core path offline, small, and honest are welcome.

## Rules that are not optional

- Do not invent a "why". Capture stores what a human or a session file actually supplied. Empty stays empty.
- Agents may draft records. Only a human may affirm. Do not weaken the non-TTY affirm gate.
- No server, database, or required LLM in the MVP. Propose those as Phase 5 issues.
- [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/): `feat:`, `fix:`, `docs:`, `test:`,
  `chore:`, `refactor:`, `ci:`. No AI attribution trailers.
- Update the spec in `docs/` in the same PR as a behavior change.
- Update `CHANGELOG.md` under `[Unreleased]`.

## Setup

```bash
uv sync --all-groups
uv run ruff check
uv run ruff format --check
uv run mypy
uv run pytest
```

Tooling: uv, hatchling (build backend), ruff (lint and format, line length 100), mypy in strict mode
with the Pydantic plugin, pytest. ty was evaluated and is still pre-1.0 beta, so mypy is the type
checker until ty is production-ready.

## Roles and permissions

Enforced by repository rulesets committed in `.github/rulesets/` and by `.github/CODEOWNERS`.

| Role | Who | Can |
|---|---|---|
| Admin | Repository owner | Everything, including bypassing every ruleset |
| Maintainer | Collaborators with write access, listed in CODEOWNERS | Review and approve PRs; merge approved PRs into `main` |
| Contributor | Anyone else | Fork, work on branches in the fork, open a PR against `main` |

- `main`, `stg`, and `dev` cannot be deleted or force-pushed by anyone but the admin.
- Changes reach `main` only through a pull request with one approval from a code owner.
  The approver must be someone other than the last pusher. New pushes dismiss earlier approvals.
  Squash or merge commits only; no rebase-merge.
- Coding agents have exactly the permissions of the account whose credentials they use.
  An agent run by the admin acts as the admin; one run by a maintainer acts as a maintainer.
  GitHub Apps and bots (for example a hosted coding-agent app) act as their own identity, not as a user,
  and get no bypass unless the admin adds them.

## Branches and issues

- One issue per branch. Branch name: `type/short-slug`.
- Every issue lives on the Whyline project board.
- Move the card to In Progress when you start, In Review when the PR opens, Done when it merges.

## Dogfooding

Once `whyline capture` works, non-trivial changes in this repo should carry a Whyline record. A draft is fine. Do not affirm a record you did not actually decide.

## Reporting issues

Use the Task or Bug issue form. Both require acceptance criteria.

Include the command, the exit code, and whether a record was draft or affirmed. Do not paste secrets; records are committed to the repo that uses the tool.
