# Coding agents

An agent recalls a reason, captures a draft, and checks that a large change has a record. It does not affirm. It does not invent `rejected`, `assumptions`, or `falsifier`.

There is one skill text. Do not fork it into a per-agent copy. `intentline install-agent` installs that text.

## Commands an agent should use

```sh
intentline why path/to/file.py:88
intentline capture --goal "the user's goal" --file path/to/file.py --pending
intentline check
```

`why` shows the status. Read it. A draft is a claim.

`capture --goal` must use the user's stated goal. `--pending` marks the id for the next commit. The record file still has to be committed (`git add .intentline`).

`check` exits 3 when the staged change is large and nothing is linked.

## Install into a repository

```sh
intentline install-agent
```

With no flags this:

- Copies the skill to `.claude/skills/intentline`, `.agents/skills/intentline`, and `.github/skills/intentline`.
- Appends the managed block from `templates/AGENTS.intentline.md` to `AGENTS.md`, between `# intentline-managed: begin` and `# intentline-managed: end`.
- Prints the MCP snippet. It does not write your MCP config.

A second run does not duplicate the block or the skill.

| Flag | Only this |
|---|---|
| `--skill` | Copy the skill into the project directories above. |
| `--agents-md` | Update the managed block in `AGENTS.md`. |
| `--mcp` | Print the MCP snippet. |
| `--claude` | Also copy the skill to `~/.claude/skills/intentline`. |
| `--hooks` | Also install the prepare-commit-msg hook. |

The opt-in pre-commit check is not part of `install-agent`. Use `intentline install-hooks --check`.

## Remove it

```sh
intentline uninstall-agent
```

Only a skill directory that contains Intentline's marker is removed, and only the files Intentline copied. A file you added beside the skill stays. In `AGENTS.md`, only the managed block is removed. Records are not deleted.

## If the command is missing

The skill's `scripts/why.sh` exits 0 and prints:

```text
No record: intentline is not on PATH.
```

`scripts/capture.sh` exits 127 when Intentline is not installed. Capture does not pretend it wrote a record.

## MCP

MCP is optional, local, and stdio-only. Install it with `uv tool install 'intentline[mcp]'`. The server does not affirm, and it does not make network calls.

```json
{
  "mcpServers": {
    "intentline": {
      "command": "intentline-mcp"
    }
  }
}
```

Tools:

| Tool | What it does |
|---|---|
| `intentline_why` | Same answers as `intentline why`. |
| `intentline_capture` | Writes a draft only. |
| `intentline_list` | Lists records. |
| `intentline_show` | One record. |
| `intentline_check` | The check verdict. `ok: false` is data. |
| `intentline_link` | Marks an id pending. It never amends HEAD. |

Resources: `intentline://schema`, `intentline://record/{id}`, `intentline://config`.

Prompt: `intentline-review`.

There is no affirm tool.

Where the JSON goes: [Claude Code](adapters/claude-code.md) and [other agents](adapters/other-agents.md).

## Errors

| Exit | When |
|---|---|
| 2 | `install-agent` was not run in a git repository. |
| 4 | This installation has no skill files to copy. |
| 5 | `--hooks` refused to write a hook. The skill copy still happened. |
