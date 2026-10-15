# Check

`intentline check` fails when a large change has no record. It does not modify the repository, and it does not invent a record.

## Staged changes

```sh
intentline check
```

Intentline counts added plus deleted lines in the staged diff. Files matched by `check.ignore` are left out (lockfiles, `.intentline/**`, and generated files, unless you change [Configuration](configuration.md)).

| Result | What you see | Exit |
|---|---|---|
| Under the threshold | `OK: 12 changed lines in staged changes, under the 30-line threshold.` | 0 |
| Large, and linked | `OK: 80 changed lines in staged changes, linked to record <id>.` | 0 |
| Large, and not linked | The line count, the file count, and a hint to run capture. | 3 |

The default threshold is 30 lines. Override it for one run:

```sh
intentline check --min-lines 50
```

A change is linked when either of these is true:

- `.intentline/pending` holds an id, or
- `HEAD` carries an `Intentline-Id` trailer.

## A range of commits

```sh
intentline check --range main..HEAD
```

The same threshold applies to the diff of that range. A trailer on any commit in the range counts as linked.

## JSON

```sh
intentline check --json
```

The document includes `ok`, `verdict`, `scope`, `changed_lines`, `min_lines`, `files`, `ignored`, and `linked_ids`. `ok: false` is data. The process still exits 3 when the change needs a record.

## As a hook

The optional pre-commit hook runs this command on the staged diff and blocks the commit only when the verdict is "needs a record." See [Hooks](hooks.md).

`git commit --no-verify` skips that hook.

## Errors

| Exit | When |
|---|---|
| 0 | The change is small enough, or it is linked. |
| 1 | `--range` or `--min-lines` is invalid. |
| 2 | Not an initialized repository. |
| 3 | The change is at or over the threshold and no record is linked. |
| 4 | The project config is corrupt. |
