# Recall

Three commands read records. None of them write.

## why

Explain a line:

```sh
intentline why src/billing/close.py:88
```

Explain a commit:

```sh
intentline why --commit HEAD
intentline why --commit a1b2c3d
```

Pass exactly one of `FILE:LINE` or `--commit`. Passing both, or neither, exits 1.

### What is included

Intentline looks at two sources:

1. `Intentline-Id` trailers on the commits that changed that line (`git log -L`).
2. Records whose `links` cover that path and line.

A goal that merely mentions the filename is not a link. The structured `links` entry has to cover the line.

Output is newest first. Each record starts with `AFFIRMED` or `DRAFT — not a confirmed reason`. Empty fields print as `(none)`.

By default, output stops at the first affirmed record. Drafts newer than that affirmed record are still shown. Older records behind it are counted:

```text
(2 older records hidden behind the affirmed one; use --all.)
```

```sh
intentline why src/billing/close.py:88 --all
```

### Nothing found

Nothing found is not an error. Intentline prints `No record explains src/billing/close.py:88` and exits 0.

In a repository with no commits yet, it prints that there are no commits yet and exits 0.

A deleted path may find nothing. `intentline show <id>` still prints the record if you have the id.

### Warnings

On stderr, not in the record text:

- A shallow clone may miss older records. Fetch the rest with `git fetch --unshallow`.
- A trailer names an id whose file is missing.
- A record file that was opened and could not be parsed.

`why` opens a record file only when the file text mentions the path, or when a trailer names that id. `intentline list` opens every file.

### JSON

```sh
intentline why src/app.py:40 --json
```

The document has `query`, `records` (each with `record`, `resolved_commits`, and `via_link`), `missing`, and `hidden`.

| Exit | When |
|---|---|
| 0 | An answer, or an honest "nothing here". |
| 1 | Both a line and `--commit`, or neither. |
| 2 | Not an initialized repository. |
| 9 | `--commit` does not name a commit. |

## show

Print one record by id:

```sh
intentline show 01a140e8-0625-7520-aa95-3b4867799050
```

The banner is `DRAFT` or `AFFIRMED`. `--json` prints the raw record with no banner.

| Exit | When |
|---|---|
| 1 | The id is malformed. |
| 2 | Not an initialized repository. |
| 4 | The file is corrupt. |
| 6 | The record uses a newer schema. |
| 9 | No record has that id. |

## list

```sh
intentline list
intentline list --status draft
intentline list --status affirmed
intentline list --path src/billing/
intentline list --author human
intentline list --author agent
intentline list --json
```

Newest first. `--path` keeps records whose link starts with that prefix. `--json` prints `{"records": [...], "skipped": [{"message", "exit_code"}]}`.

Unreadable files are skipped with a warning on stderr. The command still exits 0.

| Exit | When |
|---|---|
| 0 | The list, including an empty list (`No records.`). |
| 1 | A bad filter value. |
| 2 | Not an initialized repository. |
| 6 | The repository schema is newer than this Intentline. |
