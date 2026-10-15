# Where the skill is installed

One file, copied. Do not fork the text per agent.

| Agent | Project path |
|---|---|
| Claude Code | `.claude/skills/gitwhy/SKILL.md` |
| Generic, Copilot, agentskills.io | `.agents/skills/gitwhy/SKILL.md` |
| GitHub | `.github/skills/gitwhy/SKILL.md` |
| Claude Code (user) | `~/.claude/skills/gitwhy/SKILL.md` |

`gitwhy install-agent` copies this directory into the three project paths. `--claude` also copies it to `~/.claude/skills/gitwhy`. An agent that can only run a shell does not need the skill file: `gitwhy why FILE:LINE` and `gitwhy capture --goal "..." --pending` are enough.

Per-agent setup lives in `docs/adapters/` in the gitwhy repository.
