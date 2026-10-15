# Hooks

Intentline installs git hooks by writing a marked block into the hook file. It never replaces a hook it does not own.

## prepare-commit-msg

```sh
intentline install-hooks
```

When `.intentline/pending` holds an id, the hook appends:

```text
Intentline-Id: <id>
```

Then it clears the pending file. The hook always exits 0. A failure inside the hook prints `intentline: could not add a Intentline-Id trailer` and the commit continues without the trailer. Run `intentline link <id>` and amend, or link again on the next commit, if that happens.

The hook calls `intentline` on `PATH`. Commit with the environment that has Intentline installed.

## Optional pre-commit check

```sh
intentline install-hooks --check
```

This also installs a pre-commit hook and sets `hooks.check: true` in `.intentline/config.yml`. The hook runs `intentline check` on the staged changes.

- Exit 3 from check blocks the commit and prints the capture command.
- If Intentline is missing, or check fails for any other reason, the commit goes ahead.
- `git commit --no-verify` skips the hook.

## Run it again

`install-hooks` is safe to repeat. Only the lines between `# intentline-managed: begin` and `# intentline-managed: end` are replaced. Everything else in the hook file stays.

## When Intentline will not write the hook

Exit code 5, and the file is left unchanged, when:

- `core.hooksPath` points somewhere else, or
- The hook file already exists and does not contain Intentline's markers.

In both cases the command prints the block to add yourself.

## Remove the hooks

```sh
intentline uninstall-hooks
```

Intentline removes only its block. If the file would be left with nothing but the shebang, the file is deleted. A hook you wrote yourself is not removed.

## The hook commands

Git calls these. You do not run them by hand.

```sh
intentline hook prepare-commit-msg
intentline hook pre-commit
```

`prepare-commit-msg` always exits 0. `pre-commit` exits 3 only when the staged change needs a record.
