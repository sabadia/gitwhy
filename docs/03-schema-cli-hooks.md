# 03 — Schema, CLI, hooks, errors

**Product:** Whyline  
**Schema version:** 1  
This document is the contract. Implement it. If you must deviate, change this document in the same PR and call it out.

## 1. Record schema (version 1)

Path: `.whyline/records/<id>.yml`  
Filename is the id with hyphens, plus `.yml`.  
Encoding: UTF-8, newline at end of file, YAML 1.2, block style, no anchors, no merge keys.

```yaml
schema_version: 1
id: 01932a7e-5b1c-7c3a-8f21-9c0e4d2a1b77   # UUIDv7
status: draft                                 # draft | affirmed
created_at: 2026-10-15T13:04:11Z             # RFC3339 UTC
updated_at: 2026-10-15T13:04:11Z
affirmed_at: null                             # RFC3339 UTC or null
affirmed_by: null                             # string, free text, or null

author:
  kind: human                                 # human | agent
  name: Mahamudul                             # display name, optional
  tool: null                                  # agent tool id, e.g. claude-code, or null

goal: Close invoices at end of day, not per request.
constraints:
  - Must not change the public API response shape.
rejected:
  - option: Finalize each invoice on creation
    reason: Breaks the batch discount rule in ADR-0042
assumptions:
  - Invoices are mutable until the daily close job runs.
falsifier: A customer is charged before the daily close, or a close job no-ops while invoices stay open.
evidence:
  - kind: test                                # test | command | note
    ref: tests/test_close.py::test_daily_close
    exit_code: 0
links:
  - path: src/billing/close.py
    start_line: 80
    end_line: 140
  - path: src/billing/models.py
    start_line: null
    end_line: null
adr: docs/decisions/0042-invoice-close.md     # optional, may be null
risks:
  - Close job has no lock; concurrent closes are untested.
source:
  kind: prompt                                # prompt | flags | session | import
  ref: null                                   # path or session id, optional
```

### Field rules

| Field | Required | Rules |
|---|---|---|
| schema_version | yes | int, must be 1 for this spec |
| id | yes | UUIDv7, matches filename |
| status | yes | `draft` or `affirmed` |
| created_at, updated_at | yes | aware UTC |
| affirmed_at, affirmed_by | required if affirmed | both null if draft; both set if affirmed |
| author.kind | yes | `human` or `agent` |
| author.tool | required if agent | null if human |
| goal | yes | 1–500 characters, single line preferred, no trailing period required |
| constraints | yes | list, may be empty |
| rejected | yes | list, may be empty. Each item needs `option` (1–300 chars). `reason` may be empty string |
| assumptions | yes | list of strings, may be empty |
| falsifier | yes | string, may be empty |
| evidence | yes | list, may be empty |
| links | yes | list, must have at least one path. Lines optional |
| adr | no | string or null |
| risks | yes | list of strings, may be empty |
| source.kind | yes | `prompt`, `flags`, `session`, `import` |

Validation rejects:

- Affirmed record with empty goal.
- Affirmed record with null affirmed_at.
- Draft record with affirmed_at set.
- Unknown keys (Pydantic `extra = forbid`).
- Non-relative or absolute paths in `links` (no `..`, no leading `/`).
- Line ranges where start > end, or either line < 1.

Empty optional narrative fields are valid on drafts. They are a warning, not an error, on affirm: `whyline affirm` prints the empty fields and asks for confirmation on a TTY. With `--yes` it affirms anyway and records that confirmation was skipped (set `affirmed_by` to the value given; do not pretend the fields were filled).

### JSON Schema

Generate `schema/record.schema.json` from the Pydantic model in CI and commit it. A test fails if the committed file differs from a fresh generation.

## 2. Config schema

Project: `.whyline/config.yml`

```yaml
schema_version: 1
check:
  enabled: false                 # pre-commit runs check only if true
  min_lines: 30
  ignore:
    - "uv.lock"
    - "package-lock.json"
    - "pnpm-lock.yaml"
    - "*.lock"
    - ".whyline/**"
    - "schema/**"
    - "*generated*"
hooks:
  trailer: true
  check: false
capture:
  default_author_name: null
```

User config `~/.config/whyline/config.yml` has the same shape. Project overrides user. Flags override both.

## 3. Exit codes

| Code | Name | When |
|---|---|---|
| 0 | ok | Success |
| 1 | usage | Bad arguments (Typer default may differ — normalize to 1) |
| 2 | no_repo | Not a git repo, or whyline not initialized where required |
| 3 | check_failed | Change needs a record |
| 4 | corrupt | Record or config failed validation |
| 5 | hook_conflict | Refusing to clobber hooks |
| 6 | schema | Unsupported schema version |
| 7 | unsafe_git | Refusing amend of pushed commit, or similar |
| 8 | affirm_refused | Affirm without human gate |
| 9 | not_found | Id or path not found |

Document these in `--help` for the root command.

## 4. CLI

Root: `whyline`. Every command supports `--json` where it produces data, and `--verbose`.

### `whyline init`

Create `.whyline/config.yml`, `.whyline/schema-version`, `.whyline/records/.gitkeep` if missing. Idempotent. Refuse to overwrite a config unless `--force`.

### `whyline capture`

Create a draft record.

```
whyline capture
  [--goal TEXT]
  [--constraint TEXT]          # repeatable
  [--rejected OPTION]          # repeatable; pair with --rejected-reason in order
  [--rejected-reason TEXT]     # repeatable, aligned by index with --rejected
  [--assumption TEXT]          # repeatable
  [--falsifier TEXT]
  [--risk TEXT]                # repeatable
  [--file PATH]                # repeatable; default = staged files
  [--evidence-test REF]
  [--adr PATH]
  [--author-name TEXT]
  [--agent-tool TEXT]          # if set, author.kind = agent
  [--session PATH]             # read goal candidate only; see below
  [--pending]                  # write id to .whyline/pending for the hook
  [--affirm]                   # human gate applies
  [--yes]
```

Interactive mode (no `--goal`) asks exactly three questions, in order, and accepts empty for the last two:

1. What is this change for? (required)
2. What did you consider and reject? (optional)
3. What would prove this wrong? (optional)

Session mode (`--session PATH`):

- Accept a text or JSON file.
- Goal candidate = the first user message if JSON has a known shape, else the first non-empty line.
- Files = whatever the file lists under known keys, else leave links to staged files.
- Do not copy the session into the record. Do not parse free prose into `rejected` or `assumptions`.
- Always draft.

`--pending` writes the id, and only the id, to `.whyline/pending`. That file is gitignored via a `.whyline/.gitignore` that contains `pending`.

### `whyline affirm <id>`

Set status to affirmed, set `affirmed_at` to now, set `affirmed_by` from `--by` or from `git config user.name`.

Refuse if stdin is not a TTY, unless `--i-am-human` is passed. `--yes` skips the empty-field confirmation but does not skip the TTY / `--i-am-human` gate.

### `whyline link <id>`

Write `.whyline/pending`. With `--amend-head`: add the trailer to HEAD only if the commit is not on any remote (check `git status` / `branch -vv` and refuse if ahead-behind shows the commit is pushed, or if unsure). Default is pending-only, no amend.

### `whyline why <file:line>`

`<file:line>` is required unless `--commit` is given.

```
whyline why src/app.py:40
whyline why --commit abc123
whyline why src/app.py:40 --all
whyline why src/app.py:40 --json
```

Human output starts with a banner `AFFIRMED` or `DRAFT — not a confirmed reason`. Then goal, falsifier, rejected, assumptions, evidence, id, commit sha if known.

### `whyline show <id>`

Print one record. Exit 9 if missing.

### `whyline list`

```
whyline list [--status draft|affirmed] [--path PREFIX] [--author KIND] [--json]
```

Default sort: created_at descending.

### `whyline check`

```
whyline check [--range REVSPEC] [--min-lines N]
```

Default range is the staged diff. Exit 3 if a record is required and missing. Exit 0 otherwise. Never modifies the repo.

### `whyline install-hooks` / `whyline uninstall-hooks`

```
whyline install-hooks [--check]
whyline uninstall-hooks
```

Install a `prepare-commit-msg` hook that:

- Is idempotent and marked with a line `# whyline-managed`.
- Appends `Whyline-Id: <id>` using `git interpret-trailers` if `.whyline/pending` has an id.
- Does not add a trailer if one is already present.
- Does not fail the commit if whyline is missing from PATH; prints a warning.

`--check` also installs/enables the pre-commit check and sets `hooks.check: true` in project config.

Uninstall removes only blocks marked `# whyline-managed`. Leaves user content in the hook file.

If `core.hooksPath` is set, do not write files. Print the hook script to stdout and the config line to add. Exit 5.

### `whyline schema`

Print the JSON Schema to stdout. Used by CI and by other tools.

### `whyline version`

Print version from package metadata.

## 5. Git trailer

Key: `Whyline-Id`  
Value: the uuid  
Placement: commit message footer, blank line before trailers, via `git interpret-trailers`.

Example:

```
Close invoices in the daily job

Moves finalization out of the request path so batch discounts apply.

Whyline-Id: 01932a7e-5b1c-7c3a-8f21-9c0e4d2a1b77
```

Do not invent other trailers in v1.

## 6. Agent surfaces

Full contract: `docs/07-agent-integrations.md`. Implement that document. Summary of the CLI pieces:

### `whyline adapters claude`

Prints, and with `--write` writes, a Claude Code hook snippet. The Stop hook drafts a record from the session. It never affirms. It exits 0 on its own failure. Session file path comes from current Claude Code docs, not from memory.

### `whyline install-agent` / `whyline uninstall-agent`

```
whyline install-agent [--claude] [--skill] [--mcp] [--agents-md] [--hooks]
```

Default: install the portable skill into `.claude/skills/whyline` and `.agents/skills/whyline`, append the managed AGENTS.md block, print the MCP config snippet. `--hooks` also installs git hooks. Idempotent. Uninstall removes only `# whyline-managed` blocks.

### `whyline-mcp`

Console script, stdio only, optional extra `whyline[mcp]`. Tools: `whyline_why`, `whyline_capture`, `whyline_list`, `whyline_show`, `whyline_check`, `whyline_link`. No affirm tool. No network.

## 7. Claude Code adapter details

Ship `src/whyline/adapters/claude.py` and a template the command writes.

`whyline adapters claude` prints, and with `--write` writes, a snippet the user can merge into `.claude/settings.json`:

- A `Stop` hook that runs `whyline capture --session <transcript> --pending --agent-tool claude-code` only if the session touched files and no pending id exists.
- The transcript path must come from Claude Code's documented session file location at implementation time. Look up the current docs (`code.claude.com/docs`) when you build this. Do not guess a path. If the path is not stable, the command prints manual instructions and does not write a broken hook.

The adapter script must:

- Exit 0 on any internal failure (never block the agent).
- Write drafts only.
- Not affirm.
- Not send data anywhere.

Document the snippet in `docs/adapters/claude-code.md`.

## 7. Human output examples

`whyline why src/billing/close.py:90`

```
DRAFT — not a confirmed reason
id: 01932a7e-5b1c-7c3a-8f21-9c0e4d2a1b77
goal: Close invoices at end of day, not per request.
falsifier: A customer is charged before the daily close, or a close job no-ops while invoices stay open.
rejected:
  - Finalize each invoice on creation — Breaks the batch discount rule in ADR-0042
assumptions:
  - Invoices are mutable until the daily close job runs.
commit: abc1234 (if linked)
```

`--json` returns the raw record plus a `resolved_commits` array. No banner text in JSON.

## 8. Error messages

Every error includes:

- What happened (one sentence).
- The path or id involved.
- The next command to run, if one exists.

Bad: `Error: invalid`  
Good: `Record 0193… failed validation (.whyline/records/0193….yml): affirmed_at is null while status is affirmed. Fix the file or run whyline capture again.`

## 9. Versioning policy

- Schema version bumps only on a breaking field change.
- New optional fields with defaults are not a bump, but a reader from the previous minor must ignore unknown keys — this conflicts with `extra = forbid`. Decision: `extra = forbid` in the writer; the reader accepts unknown keys and preserves them on round-trip (`extra = allow` on read model, `forbid` on write model). Document this split in code.
- CLI flags are additive in v1. Do not rename flags after the first tagged release without a deprecation.

## 10. Dogfood

Once `capture` and `link` work, the whyline repo uses them. Add a note in `CONTRIBUTING.md`: non-trivial changes should carry a Whyline record. Do not enforce it in CI until Phase 4, and only if the maintainers still want it.
