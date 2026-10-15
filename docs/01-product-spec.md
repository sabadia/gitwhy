# 01 — Product specification

**Product:** Gitwhy  
**Status:** Locked for MVP  
**Date:** 2026-10-15

## 1. The problem

Software developers can produce code faster than they can understand it.

Three failures show up in every team that uses coding agents, and in most teams that do not:

1. **The reason dies.** A human decides to retry on 429 but not on 500, or to close invoices at end-of-day rather than per request. That decision lives in a chat, a call, or a head. Six weeks later the code is the only artifact left.
2. **Review became reverse-engineering.** Reviewers used to check a diff against an intent they shared with the author. Agent-written diffs look clean and carry no intent. Review time has risen roughly in line with the extra pull requests AI created. Reviewers either skim, or burn out doing the careful reading.
3. **The next change invents history.** A later human or agent, missing the decision, "improves" the code in a way that violates it, or rebuilds the rejected alternative. Debugging then spends hours on code that is almost right.

Evidence, 2026:

- Stack Overflow Developer Survey (30,903 developers): 63.2% cite incomplete information, 60.9% say important context lives in people's heads, 56.5% say information is outdated, 53.4% say it is spread across tools. Only 9.6% say they usually have the context they need. 79% discover important context only after starting or finishing a task. 26.1% say important decisions are hard to find later.
- Coleman Parkes survey for Undo (300 engineering leaders, mission-critical systems): 9.8 hours/week writing code, 16.9 hours/week debugging. 35% of AI-generated code reaches production before the team understands it. 79% say generation is faster and the release cycle is not.
- Review bottleneck reporting across 2026 (DORA-adjacent polls, Aviator, industry write-ups): high-AI teams merging far more PRs, review time up sharply, half of engineers in one conference poll naming review as the top SDLC friction.

Existing tools miss the hole:

- AI review bots (CodeRabbit, Greptile, Graphite, Qodo, and dozens more) comment on the diff. They do not know whether the change should exist.
- Architectural Decision Records capture the why, but they are essays, written after the fact, and they rot. Agents asked to generate them invent plausible reasons.
- Audit/provenance standards (ProvenanceCode, Decision Provenance Standard) target compliance. They are too heavy for a solo developer at 23:00.

Gitwhy is the missing artifact: a small, structured, git-native record of intent, captured when the change is made, recalled at the line.

## 2. Who it is for

Primary (MVP must serve these people with no setup beyond install and `gitwhy init`):

1. **The solo developer using coding agents.** Claude Code, Codex, Cursor, Aider, or similar. They want "why did I do this in March?" and they want the next agent session to stop re-deciding.
2. **The reviewer on a small team.** They want to answer "should this exist?" in under a minute, not reconstruct it from a 400-line diff.
3. **The person debugging a regression.** They want the assumption the change depended on, and the test that claimed to prove it.

Secondary (served by the same CLI, no extra product):

4. **The open-source maintainer** who merges drive-by agent PRs and needs a reason attached.
5. **The coding agent itself.** Claude Code, Codex, Cursor, Copilot, Gemini CLI, Aider, OpenCode, or anything that can run a shell or speak MCP. It is a first-class user, not an afterthought. It must be able to recall constraints before editing and draft a record after a change, on any project, without a custom integration written per tool.

Not the target of v1: compliance officers, regulated enterprises that need signed audit trails, teams that want a hosted dashboard. Those can come later as an export format. They must not shape the MVP.

## 3. Jobs to be done

| When I… | I want to… | So that… |
|---|---|---|
| Finish a change | Have the reason captured without writing an essay | I don't pay a documentation tax |
| Review a PR | See goal, rejected alternative, and falsifier next to the diff | I can approve or reject the intent, not just the syntax |
| Open a file months later | Ask why line 88 exists | I don't repeat a rejected design |
| Start an agent session | Hand the agent the binding decisions for the files it will touch | It doesn't invent history |
| Be a coding agent on any repo | Call a skill, an MCP tool, or the CLI to recall and draft | I don't need a one-off integration per tool |
| Hit a bug | See which assumption the relevant change declared | I debug the decision, not just the stack trace |

## 4. Product principles

1. Capture is a byproduct, or it will not happen. Agent sessions produce the draft automatically. Humans answer at most three short prompts.
2. Empty is honest. A missing "why" is an empty field, never a generated paragraph.
3. Recall is the product. Capture that nobody queries is a write-only log.
4. Git is the distribution channel. Clone the repo, get the reasons.
5. Small enough to commit. A record is a screen, not a document.
6. Status is visible. Draft and affirmed are different, and the tool says so.

## 5. MVP scope

In:

- `gitwhy init` — create `.gitwhy/` and a schema version file.
- `gitwhy capture` — write a record from flags, from a prompt (three questions), or from a session log path the user supplies.
- `gitwhy affirm <id>` — human marks a draft as affirmed.
- `gitwhy why <file:line>` — print the record(s) that explain that line.
- `gitwhy why --commit <sha>` — print the record linked to a commit.
- `gitwhy show <id>` — print one record.
- `gitwhy list` — list records, filter by status, path, author.
- `gitwhy check` — exit non-zero if the current change (staged diff, or a given commit range) has no record and exceeds a configurable line threshold.
- `gitwhy install-hooks` / `uninstall-hooks` — install a `prepare-commit-msg` hook that adds the `Gitwhy-Id` trailer, and a `pre-commit` hook that runs `check` when configured.
- `gitwhy link <id>` — attach a record id to the upcoming commit message as a trailer, or to an existing commit only with an explicit, warned amend path that refuses if the commit is pushed.
- Claude Code hook adapter: a documented `.claude/settings.json` snippet and a script that, on Stop, drafts a record from the session if one is not present.
- Portable Agent Skill at `skills/gitwhy/SKILL.md`, installed into the consumer project for Claude Code and for generic agents.
- Local stdio MCP server (`gitwhy-mcp`) with tools for why, capture, list, show, check, and link. No affirm tool. Optional extra, not a core dependency.
- `gitwhy install-agent` / `uninstall-agent` that drops the skill, the AGENTS.md snippet, and optionally hooks.
- `templates/AGENTS.gitwhy.md` snippet any project can commit so every agent sees the rules.
- JSON Schema export of the record, committed in `schema/record.schema.json`, generated from the Pydantic model so they cannot drift.
- Man-quality `--help` on every command.
- README with a 60-second quickstart and a "use from a coding agent" section.

Out:

- HTTP server, GitHub App, PR comment bot, web UI, remote MCP endpoint.
- Required LLM extraction. (A later optional command may wrap a user-supplied model. Not in MVP.)
- An MCP tool or skill action that affirms a record. Affirm stays a human CLI command.
- Per-agent forks of the skill. One skill text, copied to the paths each agent reads.
- Multi-repo federation, sync service, accounts, teams, permissions.
- Cryptographic signing of records.
- Automatic line mapping across renames beyond what `git log -L` and blame already give. Use git's own follow.
- IDE extensions beyond what MCP and the skill already provide. The CLI is the interface.

## 6. Success metrics

A developer should feel the product working in the first session. Measure:

| Metric | Target for v1 |
|---|---|
| Time to first record, no agent | Under 60 seconds from `uv tool install` equivalent / `pipx` to a committed record |
| Time to first record, with agent hook | Zero extra prompts if the session log has a user goal; otherwise one prompt |
| `gitwhy why file:line` latency | Under 100 ms on a repo with 10,000 commits and 1,000 records, warm filesystem |
| Record size | Median under 40 lines of YAML |
| False certainty | Zero. Draft records always rendered with a `DRAFT` banner |
| Core path network calls | Zero |
| Agent install | `gitwhy install-agent` on a consumer repo leaves a working skill and an AGENTS.md block; a second run does not duplicate them |
| Agent recall | An agent following the skill can answer "why does line N exist?" by running `gitwhy why` or the MCP tool, with the draft/affirmed banner intact |

Adoption signal (not a launch blocker, but the reason to exist): a developer runs `gitwhy why` on their own code at least once in the week after install, without being told to.

## 7. Non-goals

- Gitwhy is not a code reviewer. It does not say whether the code is correct.
- Gitwhy is not a memory product for chat. It does not store conversation transcripts. A session log is an input to capture, not a stored artifact (unless the user explicitly passes `--keep-source`).
- Gitwhy is not an ADR replacement for architecture. It is the change-level record. A team may still keep ADRs. Gitwhy can reference one in the `links` field.
- Gitwhy does not decide what "good" intent is. It stores what the author declared and shows the gaps.

## 8. Business shape

This is an open-source developer tool, Apache-2.0, distributed as a Python package and a console script.

- v1 value is the CLI. Free, local, no account.
- Future revenue, not designed now: a hosted team layer (shared affirmation policy, PR app, audit export) that reads the same files. The file format must stay open so the CLI is useful forever without that layer.
- Distribution: PyPI as `gitwhy`, installable with `uv tool install gitwhy` and `pipx install gitwhy`. Homebrew and a single binary are post-v1.
- The repo itself dogfoods Gitwhy once `capture` works.

No pricing, no accounts, no telemetry in v1. If telemetry is ever proposed, it is opt-in, documented, and a separate issue. Default is off, and v1 ships with none.

## 9. User-facing promises

State these in the README and do not break them:

1. Your reasons stay in your repo. We do not receive them.
2. A draft is a claim. An affirmed record is a human saying "this is the reason."
3. Uninstalling the hooks leaves your records in place. Deleting `.gitwhy/` deletes them, and git history still has the old commits.
4. The tool will not invent a reason to fill a gap.

## 10. Glossary

| Term | Meaning |
|---|---|
| Record | One YAML document describing the intent of a change |
| Draft | A record not yet affirmed by a human |
| Affirmed | A human-confirmed record |
| Trailer | The `Gitwhy-Id: <id>` line in a commit message footer |
| Hunk link | A path plus optional line range inside a record, pointing at the lines the record explains |
| Falsifier | The observation that would prove the decision wrong |
| Capture | Creating a record |
| Recall | Querying records by file, line, commit, or id |
