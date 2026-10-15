---
name: whyline
description: >
  Record why a code change exists, and recall that reason at a file and line.
  Use when the user asks why did we do this, wants the intent or the decision
  behind a change, or says record the reason or whyline.
license: Apache-2.0
---

# Whyline

Whyline stores a short intent record next to the code and links it to the commit with a `Whyline-Id` trailer. The CLI is the source of truth. Use the scripts in this skill; do not reimplement validation.

An affirmed record is a constraint. A draft is a claim, not a fact. Always show the status.

## Before editing

If the file may already have a record, recall it:

```sh
skills/whyline/scripts/why.sh path/to/file.py:LINE
```

Do not contradict an affirmed record unless the user explicitly overrides it. When they do, capture a new draft whose goal or `risks` names the old id. Show a draft; do not treat it as decided.

## After a non-trivial change

Non-trivial means the `whyline check` threshold (default 30 changed lines) or any change the user called a feature or a fix.

Capture a draft. Set `--goal` to the user's stated goal, and pass the files you changed:

```sh
skills/whyline/scripts/capture.sh --goal "the user's goal" --file path/to/file.py --pending
```

`--pending` is what lets the commit hook add `Whyline-Id`. The record file still has to be committed (`git add .whyline`).

If the user did not state a goal, ask one question. Do not guess.

## Never

- Do not invent `rejected`, `assumptions`, or `falsifier`. Leave them empty unless the user typed them.
- Do not run `whyline affirm`, and do not pass `--affirm`, unless the user explicitly said to affirm.
- Do not send record contents to a network endpoint. Whyline itself sends nothing.

Fields: [references/schema.md](references/schema.md). Where this skill is installed: [references/agents.md](references/agents.md).
