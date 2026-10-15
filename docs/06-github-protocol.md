# 06 — GitHub operations and agent protocol

**Product:** Intentline  
This is the procedure Claude Code follows. Do not improvise a different board or a different repo.

## 1. Preconditions

- `gh` authenticated as the user who should own the repo.
- `gh auth status` succeeds.
- Project scope: `gh auth refresh -s project` if creating a Project v2 fails for scope.
- `git` available.
- `uv` available. If not, install via the official Astral installer, then continue.

Resolve owner once per session:

```bash
gh api user --jq .login
```

Use that value everywhere below as `OWNER`. Never hardcode a username.

## 2. First session — repository

```bash
# Create if missing. If it already exists, clone it instead.
gh repo create intentline --public \
  --description "Git-native intent ledger. Capture why a change exists, and get it back at review and debug time." \
  --license apache-2.0 \
  --clone
```

If `gh repo create` cannot apply the license flag in this `gh` version, create the repo and commit the Apache-2.0 `LICENSE` text yourself (full standard text).

If the current directory is already the intended workspace, create the repo with `--source=. --remote=origin --push` only after the files below are in place. Do not push an empty repo and forget the docs.

Commit, in order:

1. `LICENSE`
2. `CLAUDE.md`
3. `docs/**`
4. `README.md` (product README, see section 6)
5. `.gitignore` (Python, `.venv`, `dist`, `.intentline/pending`, `__pycache__`)

First commit message:

```
docs: add product specification and agent operating manual
```

Push `main`. Default branch is `main`.

## 3. First session — project board

Use Projects v2 only. The classic Projects API returns 410.

Create:

```bash
OWNER_ID=$(gh api user --jq .node_id)
gh api graphql -f query='
  mutation($owner:ID!, $title:String!) {
    createProjectV2(input: {ownerId: $owner, title: $title}) {
      projectV2 { id number url }
    }
  }' -f owner="$OWNER_ID" -f title="Intentline"
```

Save the project id and URL in `.intentline-dev/project.json` inside the intentline repo (gitignored) and also echo them in the issue comment for 0.1 so a future session can find them via:

```bash
gh project list --owner "$OWNER" --format json
```

### Fields

Create or confirm these fields. Status already exists; rename options to match.

| Field | Type | Options |
|---|---|---|
| Status | single select | Backlog, Ready, In Progress, In Review, Done, Blocked |
| Phase | single select | 0, 1, 2, 3, 4, 5 |
| Work Type | single select | feat, fix, docs, chore, test |
| Priority | single select | P0, P1, P2, P3 |
| Area | single select | meta, core, cli, hooks, docs |

GitHub reserves the project field name `Type` (it collides with built-in issue types), so the
type field is named **Work Type**. Everywhere this doc or the roadmap says "Type" for a board
field, use `Work Type`. The `type-*` labels keep their names.

Add a Board view grouped by Status, and a Table view grouped by Phase. The GraphQL API can create
views and set visible fields but not grouping; set grouping once in the web UI.

If a GraphQL field-create call is fiddly, use `gh project field-create` (available in current gh). Look up the current `gh project --help` and use it. Do not fall back to a spreadsheet.

### Labels

Create on the repo:

`phase-0` `phase-1` `phase-2` `phase-3` `phase-4` `phase-5`  
`area-meta` `area-core` `area-cli` `area-hooks` `area-docs`  
`priority-p0` `priority-p1` `priority-p2` `priority-p3`  
`type-feat` `type-fix` `type-docs` `type-chore` `type-test`

### Milestones

`Phase 0 — Foundation`  
`Phase 1 — Schema and store`  
`Phase 2 — Capture and affirm`  
`Phase 3 — Git link and recall`  
`Phase 4 — Adapter, docs, release`  
`Phase 5 — Later`

## 4. Creating issues

For every row in `docs/04-roadmap.md`:

```bash
gh issue create --repo "$OWNER/intentline" \
  --title "0.1 Create repository, license, and project board" \
  --label "phase-0,area-meta,priority-p0,type-chore" \
  --milestone "Phase 0 — Foundation" \
  --body-file /tmp/issue-0.1.md
```

Then add it to the project and set fields:

```bash
gh project item-add PROJECT_NUMBER --owner "$OWNER" --url ISSUE_URL
# then gh project item-edit to set Status=Backlog, Phase=0, Work Type, Priority, Area
```

Look up the exact `gh project item-edit` syntax for this `gh` version. Set every field. An issue not on the board is incomplete.

Issue 0.1 may be created after the repo exists; mark it Done once the board and the rest of the issues exist.

## 5. Catch-up protocol (every later session)

Run, in order:

```bash
gh auth status
OWNER=$(gh api user --jq .login)
gh repo view "$OWNER/intentline" --json name,url,defaultBranchRef
git fetch --all --prune
git status
git log --oneline -20
gh issue list --repo "$OWNER/intentline" --state open --limit 50
gh project list --owner "$OWNER"
# list items and their Status — use gh project item-list
```

Then:

1. If any item is In Progress and assigned to this work, resume it.
2. Else if any In Review has failing CI, fix that PR.
3. Else take the Ready item with the best Priority (P0 first) in the current phase.
4. Else promote the next Backlog item in phase order to Ready and start it.

Write a one-comment session note on the issue you touch:

```
Session <YYYY-MM-DD>:
- Phase: N
- Resuming / starting: #ID title
- Done since last session: ...
- Next: ...
```

## 6. README to commit

The product README (repo root) must contain:

- One-sentence description
- The problem in four lines
- Install (`uv tool install` from a git URL until PyPI; document both)
- 60-second quickstart (init, capture, link, commit, why)
- Principles: no invented why, draft vs affirmed, local-first
- Link to `docs/01-product-spec.md`
- License Apache-2.0
- Status: pre-release, MVP in progress

Do not claim features that are not merged.

## 7. Branch, commit, PR

- Branch: `type/short-slug` from fresh `main`. Example: `feat/record-store`.
- Commits: Conventional Commits. `feat:`, `fix:`, `docs:`, `test:`, `chore:`, `refactor:`.
- No AI attribution trailers. Set Claude Code attribution to empty for this project if the setting exists (`attribution.commit` empty). Also strip any trailer a tool adds before pushing.
- PR title = commit style. Body: summary, acceptance criteria checklist, `Closes #N`.
- Move the card to In Review when the PR opens.
- Squash-merge is acceptable. Merge commits are acceptable. Do not rebase-merge if it rewrites other people's commits. Prefer squash for a clean main.
- After merge: card to Done, branch deleted, CHANGELOG updated (in the PR, not after).

## 8. Deciding and performing the next action

You are expected to continue without being told the next micro-step, as long as:

- The next action is the next issue on the board under the rules above.
- You do not cross a phase boundary without the exit criteria met, unless the user said to.
- You do not add scope. New work becomes an issue first.
- You stop and ask when:
  - `gh` auth is missing
  - A spec conflict cannot be resolved by the precedence in `CLAUDE.md`
  - A destructive git action would be required
  - Publishing to PyPI or tagging a release (always ask)
  - The user has not confirmed a product decision that the spec marks as open

When the user says "continue", "keep going", or "next", you do not ask what to do. You run catch-up and take the next issue.

When the user says "do X" and X is not an issue, create the issue, add it to the board, then do it if it is in scope. If it is out of scope (server, SaaS, required LLM), create the issue in Phase 5 and ask before building.

## 9. Staying smart across a long project

- The board is memory. Do not rely on chat history.
- Specs in `docs/` are memory. Update them when behavior changes.
- `CHANGELOG.md` is the user-facing memory.
- Session comments on issues are the agent memory.
- If you are unsure what happened, the order of trust is: code on `main`, then issue state, then comments, then chat.

## 10. Reporting

End every session with:

- Repo: `https://github.com/OWNER/intentline`
- Board: the project URL
- Completed: `#n title` list
- In progress: `#n title`
- Next if told to continue: `#n title`
- Blockers: none, or the exact question
