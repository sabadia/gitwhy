# Capture

`intentline capture` writes a draft. It does not affirm unless you pass `--affirm`, and that path has the same human gate as [Affirm](affirm.md).

Anything you do not pass stays empty. Intentline does not invent rejected alternatives, assumptions, or a falsifier.

## Flags

The usual form, after you have staged the files:

```sh
git add src/billing/close.py
intentline capture \
  --goal "Close invoices once a day." \
  --constraint "Must not change the public API response shape." \
  --rejected "Finalize each invoice on creation" \
  --rejected-reason "Breaks the batch discount rule." \
  --assumption "Invoices stay mutable until the daily close." \
  --falsifier "A customer is charged before the daily close." \
  --risk "The close job has no lock." \
  --evidence-test "tests/test_close.py::test_daily_close" \
  --file src/billing/close.py \
  --pending
```

| Option | What it does |
|---|---|
| `--goal` | The reason. 1–500 characters. Required in a non-interactive shell. |
| `--constraint` | Repeat for each constraint. |
| `--rejected` | An alternative that was considered and rejected. Repeatable. |
| `--rejected-reason` | Why the `--rejected` value in the same position was rejected. Repeatable, paired in order. |
| `--assumption` | Repeat for each assumption. |
| `--falsifier` | What would prove the decision wrong. |
| `--risk` | Repeat for each risk. |
| `--file` | A file this record explains. Repeatable. Default: the staged files. |
| `--evidence-test` | A test that supports the change. |
| `--adr` | Path to a related decision document. |
| `--author-name` | Display name. Default: `capture.default_author_name` in config, if set. |
| `--agent-tool` | Marks the author as an agent and records the tool id, for example `claude-code`. |
| `--pending` | Marks the id for the next commit. Same result as `intentline link <id>`. |
| `--session PATH` | Reads the goal from the first user message in a text or JSON session log. Nothing else in the log is copied. |
| `--affirm` | Affirm in the same step. Humans only. |
| `--yes` | With `--affirm`, do not ask about empty fields. |
| `--i-am-human` | With `--affirm`, allow a non-interactive shell. Only a human may pass this. |
| `--json` | Print one JSON document on stdout. |

`--file` paths are resolved against the repository root. A path that escapes the repository is refused.

## Interactive capture

On a terminal, omit `--goal` and Intentline asks three questions:

1. What the change is for. Required.
2. What was rejected. Optional.
3. What would prove it wrong. Optional.

A question is skipped when you already passed that flag. Without a terminal, and without `--goal` or `--session`, capture exits 1 and tells you to pass flags.

## From a session log

```sh
intentline capture --session ~/sessions/review.json --file src/app.py
```

The goal is the first user message in that file. Later messages, tool output, and anything the model said are ignored. If the log has no user message, capture exits 1.

## What you see

```text
Captured draft 01a140e8-0625-7520-aa95-3b4867799050
  .intentline/records/01a140e8-0625-7520-aa95-3b4867799050.yml
```

With `--json`, the same information is one JSON object, including `"pending": true` when you passed `--pending`.

## Two captures at once

The last write wins. The ids do not collide.

## Errors

| Exit | When |
|---|---|
| 1 | Missing goal, bad flags, or a declined affirm confirmation. |
| 2 | Not a git repository, or Intentline is not initialized. |
| 4 | The record could not be written or an existing file is corrupt. |
| 6 | The repository schema is newer than this Intentline. |
| 8 | `--affirm` was refused because this is not a human at a terminal. |

Next: [Linking commits](linking.md).
