# Records

A record is a small YAML file. It says why a change exists. It is not a design essay. Twenty lines is the right size.

Path: `.intentline/records/<id>.yml`

The filename is the id, with hyphens, plus `.yml`. Encoding is UTF-8.

## Status

| Status | Meaning |
|---|---|
| `draft` | A claim. An agent may write one. Queries label it `DRAFT — not a confirmed reason`. |
| `affirmed` | A human confirmed the reason. Queries label it `AFFIRMED`. |

Only a human may affirm. See [Affirm](affirm.md).

## Example

```yaml
schema_version: 1
id: 01932a7e-5b1c-7c3a-8f21-9c0e4d2a1b77
status: draft
created_at: 2026-10-15T13:04:11Z
updated_at: 2026-10-15T13:04:11Z
affirmed_at: null
affirmed_by: null
author:
  kind: human
  name: Ada
  tool: null
goal: Close invoices at end of day, not per request.
constraints:
  - Must not change the public API response shape.
rejected:
  - option: Finalize each invoice on creation
    reason: Breaks the batch discount rule
assumptions:
  - Invoices are mutable until the daily close job runs.
falsifier: A customer is charged before the daily close.
evidence:
  - kind: test
    ref: tests/test_close.py::test_daily_close
    exit_code: 0
links:
  - path: src/billing/close.py
    start_line: 80
    end_line: 140
adr: null
risks:
  - Close job has no lock; concurrent closes are untested.
source:
  kind: flags
  ref: null
```

Leave a list empty, and leave `falsifier` as `""`, when nobody supplied that information. Do not fill them with a plausible story.

## Fields

| Field | Rules |
|---|---|
| `schema_version` | Integer. `1` is the current schema. |
| `id` | UUIDv7. Matches the filename. |
| `status` | `draft` or `affirmed`. |
| `created_at`, `updated_at` | UTC timestamps. |
| `affirmed_at`, `affirmed_by` | Both null on a draft. Both set when affirmed. |
| `author.kind` | `human` or `agent`. |
| `author.name` | Display name. Optional. |
| `author.tool` | Required when `kind` is `agent` (for example `claude-code`). Null for a human. |
| `goal` | Required. 1–500 characters. The reason, in one line when you can. |
| `constraints` | Limits someone stated. Empty list if they named none. |
| `rejected` | Options someone considered and rejected. Each item has `option`. `reason` may be empty. |
| `assumptions` | Assumptions someone stated. Empty unless they typed them. |
| `falsifier` | What would prove this wrong. Empty string unless someone typed it. |
| `evidence` | `test`, `command`, or `note`, plus a `ref`. Empty list if there is none. |
| `links` | At least one repo-relative path. Lines are optional. |
| `adr` | Path to a related decision document, or null. |
| `risks` | Risks someone named. Empty unless they named them. |
| `source.kind` | `prompt`, `flags`, `session`, or `import`. |
| `source.ref` | Path or session id, or null. |

Links are relative to the repository root. Absolute paths and `..` are rejected.

## What validation refuses

- An affirmed record with an empty goal, or with `affirmed_at` null.
- A draft that has `affirmed_at` set.
- Unknown keys.
- A line range where the start is greater than the end, or either line is below 1.

A corrupt file fails with exit code 4. The message names the path. `intentline list` skips that file and still prints the others, with a warning. `intentline why` reports a corrupt file when that file is part of the answer.

## JSON Schema

```sh
intentline schema
```

Use the printed schema to validate a record in another tool. Exit code 0.

## Where records live

Commit `.intentline/records` with the code. A clone then has the reasons. Do not put secrets in a goal, a constraint, or any other field. Intentline does not scan for them.
