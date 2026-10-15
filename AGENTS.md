# gitwhy-managed: begin
# Gitwhy

Gitwhy stores a short record of why a change exists, next to the code, and links it to the commit with a `Gitwhy-Id` trailer. Recall that record at a file and line instead of guessing.

## Commands

- `gitwhy why path/to/file.py:88` shows the records for that line. Read the status.
- `gitwhy capture --goal "..." --pending` drafts a record from the user's stated goal and marks it for the next commit.
- `gitwhy check` exits 3 when a large change has no record.

## Rules

- Do not invent a why. Leave `rejected`, `assumptions`, and `falsifier` empty unless the user typed them.
- Do not run `gitwhy affirm`. Affirming is a human action.
- A draft is a claim, not a fact. An affirmed record is a constraint: do not contradict it unless the user explicitly overrides it, and then capture a new draft that names the old id.
- The skill is `.agents/skills/gitwhy/SKILL.md`.
# gitwhy-managed: end
