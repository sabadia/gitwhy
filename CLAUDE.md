# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Intentline (`intentline` on PyPI; the checkout directory is still named `whyline`) is a local-first, git-native intent ledger. It is a Typer CLI that stores small YAML "why" records in `.intentline/records/<uuid7>.yml`, links them to commits with an `Intentline-Id:` git trailer, and recalls them at `file:line` (`intentline why src/x.py:88`). Python 3.12+, uv, Pydantic v2, hatchling.

The maintainer spec lives in `docs/development/`. It is gitignored and may be missing from a fresh clone. Docstrings that say "docs/03 section 4" or "CLAUDE.md invariant 1" point at `docs/development/03-schema-cli-hooks.md` and `docs/development/CLAUDE.md`. When that directory exists, read `docs/development/CLAUDE.md` first: it holds the locked decisions, the product invariants, and the GitHub board workflow. Everything else under `docs/` is the public user manual and is mirrored to the GitHub wiki.

## Commands

```sh
uv sync --all-groups                 # dev deps include mcp, jsonschema, mypy
uv run ruff check
uv run ruff format --check
uv run mypy                          # strict; covers src and tests
uv run pytest --cov                  # CI fails under 90% coverage; the suite is kept at 100%
uv run pytest tests/unit/test_store.py::test_name   # run one test
INTENTLINE_BENCH=1 uv run pytest tests/bench         # opt-in timing check, not a CI gate
uv run intentline --help
```

CI runs those four checks on Python 3.12 and 3.13.

## Architecture

- `cli.py` is the only Typer layer. Each command parses flags and calls a domain module: `capture`, `link`, `recall`, `affirm`, `check`, `store`, `render`, or `config`. Domain modules raise subclasses of `errors.IntentlineError`. The CLI wrapper turns them into a message, an optional `hint`, and the error's own `ExitCode`. Exit codes 0–9 are public API: never renumber them. Every command's `--help` must list them (`tests/integration/test_readme.py` checks this).
- `models.py` defines every record shape twice. The writer models (`Record`) use `extra="forbid"`. The reader models (`StoredRecord`) use `extra="allow"`, so a record written by a newer version still loads and its unknown keys survive a round-trip. Both share generic bases, so their fields cannot drift. `schema/record.schema.json` and `tests/fixtures/schema-examples.md` must stay consistent with the models.
- `store.py` reads and writes records with atomic replace. `gitio.py` is the only module that shells out to `git`. It runs the local binary only and never touches the network.
- Linking. `intentline link <id>` (or `capture --pending`) writes `.intentline/pending`. The `prepare-commit-msg` hook (`hooks/*.sh` → `intentline hook prepare-commit-msg`) turns pending ids into trailers and never blocks a commit. `link --amend-head` refuses to rewrite a commit that any remote-tracking ref contains. The hook installer owns only the lines between the `# intentline-managed` markers.
- `recall.py` merges two sources: `Intentline-Id` trailers on the commits from `git log -L`, and records whose `links` cover the line. Results are newest first and stop at the first affirmed record unless `--all` is passed.
- `check.py` counts staged or ranged changed lines, minus `check.ignore` globs. It fails with exit 3 above `min_lines` when the change has no linked record.
- `config.py` layers config: built-in defaults < `~/.config/intentline/config.yml` (`INTENTLINE_CONFIG_HOME` overrides the location, and tests set it automatically) < `.intentline/config.yml` < flags.
- Agent surfaces:
  - `mcp.py` is a stdio server behind the optional `[mcp]` extra. Core commands must never import it.
  - `adapters/claude*.py` is the Claude Code Stop hook. It always exits 0.
  - `adapters/skill.py` runs `install-agent`.

## The skill has one source

`skills/intentline/` is the only source of the agent skill. The wheel bundles it, together with `templates/AGENTS.intentline.md`, through `force-include` in `pyproject.toml`. The copies under `.claude/skills/`, `.agents/skills/`, and `.github/skills/`, and the managed block in `AGENTS.md`, are install output. Edit `skills/intentline/` and then run `uv run intentline install-agent` to refresh them. `tests/unit/test_dogfood.py` fails if any copy differs byte-for-byte, or if this repo has fewer than three records.

## Invariants that shape the code

- No invented why. Capture copies narrative fields verbatim and never fills `rejected`, `assumptions`, or `falsifier`. Session parsing takes only the first user message and a top-level `files` list.
- Only a human affirms. Never run `intentline affirm`. Never expose affirm through MCP or the skill. Non-interactive affirm is refused without `--i-am-human`.
- The core path makes no network calls and pulls in no LLM, database, or web framework.
- Records are small (about 20 lines). Drafts are always labeled as claims when shown.

## Repo conventions

- Use Conventional Commits. Add no AI attribution trailers; `.claude/settings.json` turns attribution off.
- Non-trivial changes carry an intentline record. Run `uv run intentline capture --goal "<the user's stated goal>" --pending`, then commit `.intentline/records/` with the change. Leave a draft as a draft.
- A new behavior needs a test that includes a failure path. Unit tests go in `tests/unit/`. Integration tests go in `tests/integration/` and use the `git_repo` fixture, which creates temporary git repos. Use `conftest.plain()` to compare Rich/ANSI output.
- Several tests assert on documentation text: the README, `CONTRIBUTING.md`, `docs/adapters/*`, `CHANGELOG.md` `[Unreleased]`, and the issue forms. Check those tests before you reword those files.
- Add user-facing changes to `CHANGELOG.md` under `[Unreleased]`. `main` is protected. Open PRs against it.
