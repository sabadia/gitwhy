# Contributing to Whyline

Whyline is a local-first CLI. Contributions that keep the core path offline, small, and honest are welcome.

## Rules that are not optional

- Do not invent a "why". Capture stores what a human or a session file actually supplied. Empty stays empty.
- Agents may draft records. Only a human may affirm. Do not weaken the non-TTY affirm gate.
- No server, database, or required LLM in the MVP. Propose those as Phase 5 issues.
- Conventional Commits. No AI attribution trailers.
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

## Branches and issues

- One issue per branch. Branch name: `type/short-slug`.
- Every issue lives on the Whyline project board.
- Move the card to In Progress when you start, In Review when the PR opens, Done when it merges.

## Dogfooding

Once `whyline capture` works, non-trivial changes in this repo should carry a Whyline record. A draft is fine. Do not affirm a record you did not actually decide.

## Reporting issues

Include the command, the exit code, and whether a record was draft or affirmed. Do not paste secrets; records are committed to the repo that uses the tool.
