# Intentline documentation

Intentline stores a short record of why a change exists, next to the code, and returns that record at a file and line, a commit, or a review.

These pages are the manual. Each one has the command, the options, an example, and the errors you can hit.

## Start here

| Guide | What it covers |
|---|---|
| [Installation](installation.md) | PyPI, git, the MCP extra, and upgrading |
| [Getting started](getting-started.md) | First repository, first record, first recall |
| [Records](records.md) | The YAML record, every field, draft and affirmed |
| [Capture](capture.md) | Writing a draft from flags, a prompt, or a session log |
| [Linking commits](linking.md) | The `Intentline-Id` trailer and `--amend-head` |
| [Recall](recall.md) | `why`, `show`, and `list` |
| [Affirm](affirm.md) | How a human confirms a reason |
| [Check](check.md) | Failing a large change that has no record |
| [Hooks](hooks.md) | prepare-commit-msg and the optional pre-commit check |
| [Configuration](configuration.md) | Project config, user config, and ignore rules |
| [Coding agents](agents.md) | The skill, MCP, and `install-agent` |
| [Claude Code](adapters/claude-code.md) | Skill, MCP, and the Stop hook |
| [Other agents](adapters/other-agents.md) | Codex, Cursor, Copilot, and the shell |
| [Exit codes](exit-codes.md) | 0 through 9 |
| [Limits](limits.md) | Shallow clones, submodules, secrets, and the rest |
| [Troubleshooting](troubleshooting.md) | What to do when a command refuses |
| [Contributing](contributing.md) | How to change this codebase |

## One rule

Do not invent a why. If a person did not supply a field, leave it empty. A draft is a claim. Only a human may affirm.
