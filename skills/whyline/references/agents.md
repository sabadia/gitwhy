# Where the skill is installed

One file, copied. Do not fork the text per agent.

| Agent | Project path |
|---|---|
| Claude Code | `.claude/skills/whyline/SKILL.md` |
| Generic, Copilot, agentskills.io | `.agents/skills/whyline/SKILL.md` |
| GitHub | `.github/skills/whyline/SKILL.md` |
| Claude Code (user) | `~/.claude/skills/whyline/SKILL.md` |

`whyline install-agent` performs the project copies. An agent that can only run a shell does not need the skill file: `whyline why FILE:LINE` and `whyline capture --goal "..." --pending` are enough.

Per-agent setup lives in `docs/adapters/` in the whyline repository.
