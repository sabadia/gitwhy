# 04 — Roadmap and issue catalog

**Product:** Intentline  
Claude Code must create one GitHub issue per row below, add it to the Intentline project, and set the fields. Titles must match. Acceptance criteria must be pasted into the issue body.

Do not start a phase until the previous phase's exit criteria are Done, unless the user explicitly overrides.

Estimates are for sequencing, not for a deadline.

## Phase 0 — Foundation

Exit: repo exists, board exists, CI is green on an empty-ish package, docs are in `main`.

| # | Title | Type | Priority | Area | Acceptance criteria |
|---|---|---|---|---|---|
| 0.1 | Create repository, license, and project board | chore | P0 | meta | Public repo `intentline` under the authenticated user. Apache-2.0 LICENSE. README from docs. Project v2 with fields Status, Phase, Type, Priority, Area. All issues in this doc exist and are on the board. |
| 0.2 | Initialize uv project and tooling | chore | P0 | meta | `pyproject.toml` with hatchling, src layout, Python >=3.12, Typer, Pydantic v2, PyYAML. `uv.lock` committed. ruff and mypy configured. `uv run ruff check`, `uv run mypy`, `uv run pytest` succeed. Console script `intentline` points at `intentline.cli:app`. |
| 0.3 | Add CI workflow | chore | P0 | meta | GitHub Actions on push and PR to `main`. Runs ruff, mypy, pytest on 3.12 and 3.13. Fails the check on any failure. No secrets required. |
| 0.4 | Add CHANGELOG, CONTRIBUTING, and issue templates | docs | P1 | meta | Keep-a-changelog format. CONTRIBUTING states conventional commits, the affirm rule, and "do not invent a why". Issue template asks for acceptance criteria. |

## Phase 1 — Schema and store

Exit: records can be written and read with validation; corrupt files fail cleanly; schema JSON is generated.

| # | Title | Type | Priority | Area | Acceptance criteria |
|---|---|---|---|---|---|
| 1.1 | Implement Pydantic record and config models | feat | P0 | core | Models match docs/03 exactly. extra=forbid on write. Round-trip test for the example YAML in that doc. |
| 1.2 | Implement atomic record store | feat | P0 | core | `save`, `load`, `list` under `.intentline/records`. Temp file + rename. Rejects absolute paths and `..` in links. Unit tests for happy path and corrupt YAML. |
| 1.3 | Implement schema version gate | feat | P0 | core | Reader rejects schema_version greater than supported with exit code 6. Test covers it. |
| 1.4 | Generate and commit JSON Schema | feat | P1 | core | `intentline schema` prints JSON Schema. `schema/record.schema.json` committed. Test fails on drift. |
| 1.5 | Implement `intentline init` | feat | P0 | cli | Idempotent. Creates config, schema-version, records dir, `.intentline/.gitignore` containing `pending`. Refuses to clobber config without `--force`. |

## Phase 2 — Capture and affirm

Exit: a human can create a draft, affirm it, and see it on disk. An agent-shaped invocation cannot affirm without the human gate.

| # | Title | Type | Priority | Area | Acceptance criteria |
|---|---|---|---|---|---|
| 2.1 | Implement `intentline capture` flags mode | feat | P0 | cli | All flags in docs/03 work. Writes a valid draft. `--pending` writes `.intentline/pending`. Tests use `tmp_path` and a real git repo. |
| 2.2 | Implement interactive capture | feat | P0 | cli | Three questions, last two optional. Non-TTY without `--goal` exits 1 with a message to pass flags. |
| 2.3 | Implement session capture without invention | feat | P0 | cli | `--session` sets goal from the first user message or first line only. Does not fill rejected, assumptions, or falsifier from prose. Test with a fixture session that contains tempting prose. |
| 2.4 | Implement `intentline affirm` with human gate | feat | P0 | cli | TTY required unless `--i-am-human`. Sets affirmed_at and affirmed_by. Refuses to affirm a missing id (exit 9). Test the non-TTY refusal (exit 8). |
| 2.5 | Implement `intentline show` and `intentline list` | feat | P1 | cli | Filters for status and path. `--json` is stable. Human output includes the DRAFT/AFFIRMED banner. |

## Phase 3 — Git link and recall

Exit: a commit can carry `Intentline-Id`, and `intentline why file:line` returns the record.

| # | Title | Type | Priority | Area | Acceptance criteria |
|---|---|---|---|---|---|
| 3.1 | Implement git trailer helper | feat | P0 | core | Uses `git interpret-trailers`. Parses `Intentline-Id` from a message. Unit tests with fixture messages, including coexisting `Signed-off-by`. |
| 3.2 | Implement `intentline link` | feat | P0 | cli | Writes pending. `--amend-head` refuses if the commit appears pushed (exit 7). Test the refusal. |
| 3.3 | Implement prepare-commit-msg hook installer | feat | P0 | hooks | `install-hooks` writes a marked block. Second install is idempotent. Does not clobber a foreign hook (exit 5). `uninstall-hooks` removes only the marked block. |
| 3.4 | Implement `intentline why` by file:line | feat | P0 | cli | Uses git to find candidate commits, then loads linked records. Shows DRAFT banner. `--all` shows more than the first hit. `--commit` works. Integration test in a temp repo with two commits. |
| 3.5 | Implement `intentline check` | feat | P0 | cli | Exit 3 when staged diff exceeds min_lines and no pending/trailer. Exit 0 under the threshold, on ignored files, and when a record is linked. |
| 3.6 | Optional pre-commit check hook | feat | P1 | hooks | Off by default. `--check` enables it. Failure message includes the capture command. |

## Phase 4 — Agent surfaces, docs, release

Exit: any coding agent can use Intentline via the skill, the MCP server, or the CLI; README quickstart works; v0.1.0 is tagged only after the user says so.

| # | Title | Type | Priority | Area | Acceptance criteria |
|---|---|---|---|---|---|
| 4.1 | Portable Agent Skill | feat | P0 | hooks | `skills/intentline/SKILL.md` exists with valid frontmatter (`name`, `description`). Description says when to use it. Body forbids inventing why and forbids affirm. `scripts/capture.sh` and `scripts/why.sh` call the CLI. references/ holds the short schema note. |
| 4.2 | `intentline install-agent` and AGENTS.md snippet | feat | P0 | cli | Installs skill into `.claude/skills/intentline` and `.agents/skills/intentline`. Appends `templates/AGENTS.intentline.md` inside a managed block. Second run does not duplicate. Uninstall removes only managed blocks. |
| 4.3 | Local stdio MCP server | feat | P0 | hooks | `intentline-mcp` entry point. Optional extra; core install does not depend on it. Tools match docs/07. No affirm tool. Smoke test: capture then why in a temp repo. No network calls. |
| 4.4 | Claude Code hooks and adapter command | feat | P0 | hooks | `intentline adapters claude` prints a snippet. Stop hook drafts only, exits 0 on failure, never affirms. Session path verified against current Claude Code docs in the PR. |
| 4.5 | Per-agent docs | docs | P0 | docs | `docs/adapters/claude-code.md` and `docs/adapters/other-agents.md`. README section "Use from a coding agent". |
| 4.6 | README quickstart and man-quality help | docs | P0 | docs | README has install, init, capture, commit, why — in under 60 seconds of reading. Every command `--help` lists flags and exit codes. |
| 4.7 | Dogfood on this repo | chore | P1 | meta | At least three real records in `.intentline/records` for real changes. This repo's own agent skill is installed. CONTRIBUTING mentions the practice. |
| 4.8 | Benchmark the why path | test | P2 | core | Fixture repo with 1,000 records. `why` completes under 100 ms locally. Record the number in the PR. Optimize only if it misses. |
| 4.9 | Tag v0.1.0 and publish workflow (dry-run) | chore | P0 | meta | Version 0.1.0. GitHub release notes from CHANGELOG. PyPI publish workflow present but does not run until the user says to publish. |

## Phase 5 — Later, do not build unless asked

Create these issues as Backlog, Priority P3, so they are not forgotten. Do not implement them in v1.

| # | Title | Notes |
|---|---|---|
| 5.1 | Marketplace listing for the skill | Only after the skill is stable |
| 5.2 | Codex-specific hook if the shell path proves insufficient | Prefer the shared skill first |
| 5.3 | Optional `intentline extract` using a user-configured model | Off by default, never required, must not invent rejected/assumptions without a quoted span |
| 5.4 | GitHub Action for check | Separate repo or `action/` dir; not a server |
| 5.5 | Editor extension beyond MCP | Reads the same files |
| 5.6 | Remote MCP endpoint | Explicit non-goal until a user asks. v1 is stdio only |
| 5.7 | Signed records | Explicit non-goal until a user asks |

## Issue body template

Use this for every issue:

```
## Why
<one or two sentences from the phase goal>

## Acceptance criteria
- [ ] ...
- [ ] Tests cover the failure path named in the criteria
- [ ] Docs / --help updated if user-facing
- [ ] `uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest` pass

## Spec
docs/0X-....md section Y

## Out of scope
<what this issue must not pull in>
```

## Phase exit reporting

When a phase's exit criteria are met, comment on the phase tracking issue, move it to Done, and tell the user in the session report. Then promote the first issue of the next phase to Ready.
