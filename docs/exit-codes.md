# Exit codes

`intentline --help` lists these. They do not change between versions.

| Code | Name | When |
|---|---|---|
| 0 | ok | Success, including "nothing found" from `why` and a passing `check`. |
| 1 | usage | Unknown command, missing argument, or other bad input. |
| 2 | no repo | Not a git repository, or Intentline is not initialized where the command requires it. |
| 3 | check failed | `intentline check` found a large change with no record. |
| 4 | corrupt | A record or config file failed to parse or validate. |
| 5 | hook conflict | Intentline refused to overwrite a hook it does not own. |
| 6 | schema | A record or the repository schema is newer than this Intentline. Upgrade. |
| 7 | unsafe git | `--amend-head` would rewrite a commit that looks pushed, or a merge or rebase is in progress. |
| 8 | affirm refused | Affirm was asked for without a human at the gate. |
| 9 | not found | Unknown record id, or unknown commit. |

A command's own `--help` names the codes that command uses.

`--json` still uses these process exit codes. The JSON document is on stdout. Warnings and prompts stay on stderr.

The prepare-commit-msg hook is the exception that always exits 0, so a hook failure cannot block a commit. See [Hooks](hooks.md).
