# Limits

These are accepted limits of the current release. The commands tell you when one of them applies.

## Amend and remotes

`--amend-head` treats a commit as pushed when any remote-tracking ref in this clone contains it. That check does not contact the network. A remote that this clone has not fetched is invisible to the check. Fetch before you amend if you need that remote's view.

On a detached HEAD, capture and link-to-pending still work. `--amend-head` refuses.

## Aborted commits

If you abort a commit after the prepare-commit-msg hook runs, the pending mark is already gone. The commit was not created. Run `intentline link <id>` again.

## Shallow clones

A shallow clone may miss older records. `intentline why` says so on stderr. `git fetch --unshallow` restores the history the trailers point at.

## Submodules

Intentline uses the repository you are in. Inside a submodule, that is the submodule, not the parent.

## Deleted paths

On a deleted path, `why` may find nothing. `intentline show <id>` still prints the record.

## Empty repository

`init` and `capture` work before the first commit. `why` says there are no commits yet and exits 0.

## Concurrent capture

Two captures at once: the last write wins, and the ids do not collide.

## Secrets

Records are committed with the code. Do not put secrets in goals or any other field. Intentline does not scan for them.

## Binary files

Binary files in a diff are ignored for line links. The command does not crash on them.

## Merge commits

A trailer on a merge commit still works. `why` uses the commit that last changed the line.

## Windows

Paths are handled with `pathlib`. CI runs on Ubuntu. Quote paths that contain spaces when you call the hook scripts from a shell.

## What Intentline does not do

- It does not call an LLM.
- It does not phone home.
- It does not store records outside the repository, except the local pending file and your user config.
- It does not affirm on behalf of an agent.
