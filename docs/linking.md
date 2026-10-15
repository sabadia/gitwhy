# Linking commits

The link between a commit and a record is a git trailer:

```text
Intentline-Id: 01a140e8-0625-7520-aa95-3b4867799050
```

The YAML file is the body. The trailer is the pointer. Both travel with clone and fork. There is no server.

## Link the next commit

```sh
intentline link 01a140e8-0625-7520-aa95-3b4867799050
git add .intentline
git commit -m "feat: close invoices once a day"
```

`link` writes the id to `.intentline/pending`. That file is gitignored. The prepare-commit-msg hook reads it, appends the trailer, and deletes the pending mark.

You see:

```text
Linked 01a140e8-0625-7520-aa95-3b4867799050 to your next commit (.intentline/pending).
```

If another id was already pending, Intentline replaces it and tells you which id it replaced. One commit gets one pending id.

## If the commit is aborted

The hook runs before git finishes the commit. If you abort after that, the pending mark is already gone and the commit does not exist. Run `intentline link <id>` again, then commit.

## Amend the last commit

```sh
intentline link 01a140e8-0625-7520-aa95-3b4867799050 --amend-head
```

This changes only the commit message. Staged changes are not included. Intentline refuses `--amend-head` when:

- Any remote-tracking ref in this clone already contains HEAD. That check does not contact the network.
- HEAD is detached.
- A merge or rebase is in progress.
- HEAD is already linked to a different record.

If HEAD already carries this same id, Intentline prints that nothing changed.

## What gets committed

Commit the record file with the code:

```sh
git add .intentline
git commit -m "feat: close invoices once a day"
```

A trailer without the YAML file still names an id. `intentline why` then warns that the record is missing. A YAML file without a trailer is still found when its `links` cover the line. Use both.

## Errors

| Exit | When |
|---|---|
| 1 | The id is malformed, there is no commit to amend, or HEAD is linked to a different record. |
| 2 | Not an initialized repository. |
| 4 | The record file is corrupt. |
| 7 | Amending would be unsafe. |
| 9 | No record has that id. |

`--json` prints `id`, `pending`, `amended`, `already_linked`, and `replaced_pending`.

Install the hook with [Hooks](hooks.md) before you rely on the trailer.
