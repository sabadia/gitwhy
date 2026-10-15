# Troubleshooting

Match the message, then the exit code. `intentline <command> --help` names the codes for that command. The full table is [Exit codes](exit-codes.md).

## `intentline: not found` or exit 127

The command is not on `PATH`.

```sh
uv tool install intentline
intentline version
```

Open a new shell if the tool directory was just added to `PATH`.

The skill scripts behave differently on purpose. `why.sh` exits 0 and prints `No record: intentline is not on PATH.` `capture.sh` exits 127 so an agent does not think a draft was written.

## Exit 2, not a git repository or not initialized

Run the command from inside the repository.

```sh
intentline init
```

`init` itself exits 2 when the directory is not a git repository. `git init` first.

## Exit 6, schema is newer

This Intentline is older than the repository.

```sh
uv tool upgrade intentline
```

Intentline will not read a schema it does not know.

## Exit 4, corrupt record or config

The message names the file. Open that YAML. Unknown keys, a bad timestamp, an absolute link path, or a draft that has `affirmed_at` set are typical causes.

`intentline list` still prints the records that parsed. `intentline show <id>` is how you inspect one file on purpose.

To reset project config without deleting records:

```sh
intentline init --force
```

## Exit 5, hook was not written

The hook file already belongs to something else, or `core.hooksPath` is set. Intentline prints the block to add. Paste it between the markers it shows, and leave the rest of the file alone.

## Exit 7, amend refused

`--amend-head` thinks HEAD is already on a remote-tracking branch, or a merge or rebase is in progress, or HEAD is detached.

```sh
git status
git fetch
```

Link the record to a new commit instead:

```sh
intentline link <id>
git add .intentline
git commit -m "chore: record why"
```

## Exit 8, affirm refused

You are not on a terminal, or an agent tried to affirm. Affirm from your own terminal. See [Affirm](affirm.md). Do not pass `--i-am-human` from an agent.

## Exit 9, unknown id

The id is well formed and the repository is initialized, but `.intentline/records/<id>.yml` is not there. `intentline list` shows the ids that exist. A trailer can name an id that was never committed. Commit the record file.

## The trailer is missing after commit

The hook did not see `intentline` on `PATH`, or pending was empty.

```sh
command -v intentline
intentline link <id>
git commit --amend
```

Use `--amend` only when [Linking commits](linking.md) says amend is safe. Otherwise make a new commit.

## `why` finds nothing for a line you just changed

- The record was not committed.
- The link path does not cover that line. `start_line` and `end_line` are inclusive. Omit both to cover the whole file.
- The trailer is on a commit that is not in this clone. A shallow clone warns about that.
- You are inside a submodule. Intentline reads the submodule's `.intentline`, not the parent's.

## `why` is slow to start

The query itself reads local files. Starting the Python process is separate and is often slower than the query. `intentline version` shows that startup cost on its own.

## MCP server does not start

```sh
uv tool install 'intentline[mcp]'
command -v intentline-mcp
```

The config must use `"command": "intentline-mcp"`. Cursor also needs `"type": "stdio"`. There is no remote URL. The server does not affirm.
