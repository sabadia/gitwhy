# Getting started

This walkthrough creates one draft, links it to a commit, and reads it back at a line.

## 1. Initialize the repository

From the root of a git repository:

```sh
cd your-repo
intentline init
```

Intentline creates:

| Path | What it is |
|---|---|
| `.intentline/config.yml` | Project settings. Safe to commit. |
| `.intentline/schema-version` | The schema this repository was initialized with. |
| `.intentline/records/` | One YAML file per record. Commit this directory. |
| `.intentline/.gitignore` | Ignores `.intentline/pending`, which is local. |

Commit that directory so the records travel with clone and fork:

```sh
git add .intentline
git commit -m "chore: initialize intentline"
```

Run `intentline init` again any time. Existing records are left alone. `--force` rewrites only `config.yml`. `--verbose` also lists files that were already present.

Outside a git repository, `init` exits 2.

## 2. Install the commit hook

```sh
intentline install-hooks
```

The prepare-commit-msg hook adds an `Intentline-Id` trailer when a record is pending. It never blocks a commit. Details are in [Hooks](hooks.md).

## 3. Capture a draft

Stage the file the record explains, then capture:

```sh
git add src/app.py
intentline capture --goal "Close invoices once a day."
```

You see:

```text
Captured draft 01a140e8-0625-7520-aa95-3b4867799050
  .intentline/records/01a140e8-0625-7520-aa95-3b4867799050.yml
```

The id is a UUIDv7. The file is the record. Fields you did not pass stay empty. Intentline does not invent them.

## 4. Link the record to the next commit

```sh
intentline link 01a140e8-0625-7520-aa95-3b4867799050
git add .intentline
git commit -m "feat: close invoices once a day"
```

The hook prints `intentline: added Intentline-Id: ...` and the commit message ends with:

```text
Intentline-Id: 01a140e8-0625-7520-aa95-3b4867799050
```

`intentline capture --pending` is the same mark as `intentline link <id>`. If you abort the commit after the hook runs, that mark is already gone. Run `intentline link <id>` again.

## 5. Read it back

```sh
intentline why src/app.py:1
```

The output starts with `DRAFT — not a confirmed reason` and includes the goal. A draft is a claim, not a confirmed fact. A human affirms it later with [Affirm](affirm.md).

## Where to go next

- Every field: [Records](records.md)
- More ways to capture: [Capture](capture.md)
- Find a reason during review: [Recall](recall.md)
- Require a record on large changes: [Check](check.md)
- Let an agent draft, and only draft: [Coding agents](agents.md)
