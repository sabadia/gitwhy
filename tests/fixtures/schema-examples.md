# Schema examples used by tests

These blocks match the record and config examples. They are test input, not the user manual.

## 1. Record schema

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

## 2. Config schema

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
    - ".intentline/**"
    - "schema/**"
    - "*generated*"
hooks:
  trailer: true
  check: false
capture:
  default_author_name: null
```
