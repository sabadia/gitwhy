# Changelog

All notable changes to Gitwhy are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-10-15

### Added

- Version 0.1.0. The project name is Gitwhy. The notes for the GitHub release are this section. `.github/workflows/publish.yml` builds the package and runs `uv publish --dry-run`. It uploads to PyPI when the repository variable `GITWHY_PUBLISH` is `true`, authenticating with the `UV_PUBLISH_TOKEN` repository secret.
- `why` on 1,000 records stays under the 100 ms budget. Parsing every record took 728 ms, so a record file is parsed only when its text mentions the path. Local `why_line` median was 75 ms and 84 ms on two runs. The timing test is opt-in (`GITWHY_BENCH=1`) and is not a CI gate. A fresh process is slower: interpreter startup alone (`gitwhy version`) is about 117 ms.
- This repo dogfoods Gitwhy: `.gitwhy/records` holds a draft for the contributing practice, the installed skill, and the guard test. `gitwhy install-agent` has been run here. CONTRIBUTING states the practice. Records stay drafts, with `rejected`, `assumptions`, and `falsifier` empty.
- Product README: install from git until PyPI (not published yet), a quickstart (init, hooks, capture, link, commit, why), and the accepted limits (remote-tracking amend check, aborted commits, shallow clones, submodules, deleted files, empty repos, concurrent capture, secrets). Every command's `--help` names its exit codes.
- Docs for coding agents: README section "Use from a coding agent", and `docs/adapters/other-agents.md` for Codex, Cursor, Copilot, and the shell fallback. `docs/adapters/claude-code.md` now leads with install, MCP, then the Stop hook.
- `gitwhy adapters claude` prints a Claude Code Stop hook, and `--write` merges it into `.claude/settings.json` without changing other keys. `gitwhy adapters claude-stop` reads `transcript_path` from the hook's stdin and writes one draft when the session lists files or something is staged and `.gitwhy/pending` is empty. It never affirms, and it exits 0 when gitwhy or the session file is missing. `templates/claude-plugin/` is a hook-only plugin. The skill stays the one copy from `gitwhy install-agent`.
- `gitwhy-mcp` is a local stdio MCP server (optional extra `gitwhy[mcp]`, official `mcp` 2.3.0). Tools: `gitwhy_why`, `gitwhy_capture`, `gitwhy_list`, `gitwhy_show`, `gitwhy_check`, `gitwhy_link`. Capture writes a draft only. There is no affirm tool. Resources: `gitwhy://schema`, `gitwhy://record/{id}`, `gitwhy://config`. Prompt: `gitwhy-review`.
- `gitwhy install-agent` copies the portable skill into `.claude/skills/gitwhy`, `.agents/skills/gitwhy`, and `.github/skills/gitwhy`, appends `templates/AGENTS.gitwhy.md` to `AGENTS.md` inside a `# gitwhy-managed` block, and prints the MCP snippet (Claude Code `.mcp.json`, Cursor `.cursor/mcp.json`, Codex `config.toml`). A second run does not duplicate any of it. `--claude` also copies the skill to `~/.claude/skills/gitwhy`. `--hooks` installs the prepare-commit-msg hook. `gitwhy uninstall-agent` removes only those managed copies and blocks, and leaves text you wrote.
- Portable agent skill at `skills/gitwhy/`: `SKILL.md` tells an agent when to recall a reason and when to capture a draft, and forbids inventing fields or affirming. `scripts/capture.sh` and `scripts/why.sh` call the CLI. `capture.sh` fails if gitwhy is missing; `why.sh` exits 0 and says there is no record.
- Product specification, architecture, schema contract, roadmap, quality bar, agent integration contract, and Claude Code operating manual.
- Python package skeleton: uv project with hatchling, `src/` layout, `gitwhy` console script with a `version` command, ruff, mypy strict, and pytest.
- CI on GitHub Actions: ruff check, ruff format --check, mypy, and pytest with coverage on Python 3.12 and 3.13 for pushes to `main` and pull requests.
- Task and Bug issue forms that require acceptance criteria.
- Repository rulesets and CODEOWNERS: only the admin may delete or force-push `main`, `stg`, or `dev`; `main` changes only through code-owner-approved pull requests.
- Record and config models (`gitwhy.models`) matching the schema v1 contract: UUIDv7 ids, UTC timestamps, draft/affirmed consistency, repo-relative link paths, and a writer/reader split that keeps unknown keys on read.
- Typed error hierarchy with the stable exit codes from the spec (`gitwhy.errors`).
- Atomic record store (`gitwhy.store.RecordStore`): save, load, and list under `.gitwhy/records`; temp file + rename; corrupt files fail cleanly with the path and a next step.
- Schema version gate: a record or a `.gitwhy/schema-version` newer than this gitwhy is refused with exit code 6 and an upgrade hint, never guessed at.
- `gitwhy schema` prints the record JSON Schema (draft 2020-12); the same schema is committed as `schema/record.schema.json` and a test fails if they drift.
- Root `--help` lists the exit codes.
- `gitwhy init` creates `.gitwhy/` (config, schema-version, records, and a `.gitignore` for the local pending file) at the repository root. Safe to rerun; `--force` resets only the config and never touches records.
- Layered config loading: built-in defaults < user config (`$GITWHY_CONFIG_HOME`, `$XDG_CONFIG_HOME/gitwhy`, or `~/.config/gitwhy`) < project `.gitwhy/config.yml`.
- `gitwhy show <id>` prints one record under a DRAFT or AFFIRMED banner, showing empty fields as `(none)`; `gitwhy list` lists records newest first with `--status`, `--path`, `--author`, and `--json`, warning on and skipping unreadable files.
- `gitwhy affirm <id>` marks a draft as affirmed. It is refused (exit 8) from a non-interactive shell unless `--i-am-human` is passed; empty narrative fields need confirmation on a terminal (`--yes` skips it) and are never filled in. `--by` defaults to git `user.name`.
- `gitwhy capture` (flags mode) writes a draft record from `--goal` and the other docs/03 flags, linked to the staged files or `--file` paths. Fields you leave out stay empty; `--pending` marks the id in `.gitwhy/pending` for the next commit.
- `gitwhy capture --affirm` lets a human affirm in the same step, through the same human gate as `gitwhy affirm` (`--i-am-human`, `--yes`); a refusal or a declined confirmation writes nothing.
- Interactive `gitwhy capture`: without `--goal` on a terminal it asks what the change is for (required), what was rejected (optional), and what would prove it wrong (optional), skipping questions whose flags were given. Without a terminal it exits 1 and asks for flags.
- `gitwhy capture --session PATH` takes the goal from a session log's first user message (plain text, a JSON message list, or JSONL such as a Claude Code transcript) and links a top-level `files` list if present. Nothing else is read from the session: rejected alternatives, assumptions, and the falsifier stay empty, session captures are always drafts, and only the file name of a session outside the repository is recorded.
- Git trailer helper (`gitwhy.gitio`): reads `Gitwhy-Id` trailers and adds one through `git interpret-trailers`, alongside `Signed-off-by` and other trailers, never replacing an existing link.
- `gitwhy link <id>` marks a record for the next commit via `.gitwhy/pending`; `--amend-head` adds the `Gitwhy-Id` trailer to HEAD's message instead, refusing (exit 7) when HEAD is already on a remote-tracking branch, detached, or mid-merge/rebase, and never replacing an existing link.
- `gitwhy install-hooks` / `uninstall-hooks`: a `prepare-commit-msg` hook that adds `Gitwhy-Id` from `.gitwhy/pending` and clears it. It never blocks a commit, never overwrites a foreign hook (exit 5, prints the lines to add), writes nothing when `core.hooksPath` is set (exit 5), and uninstall removes only gitwhy's marked block.
- `gitwhy why FILE:LINE` shows the records that explain a line, newest first, from the `Gitwhy-Id` trailers of the commits that changed it (`git log -L`) and from records whose links cover it. Each starts with AFFIRMED or `DRAFT — not a confirmed reason`; output stops at the first affirmed record unless `--all`. `--commit SHA` explains a commit; `--json` returns raw records with `resolved_commits`.
- `gitwhy check [--range A..B] [--min-lines N] [--json]` exits 3 when a change reaches the line threshold (default 30) with no record linked through `.gitwhy/pending` or a `Gitwhy-Id` trailer, and prints the capture command. Files matched by `check.ignore` don't count. It never modifies the repository.
- `gitwhy install-hooks --check` adds an opt-in `pre-commit` hook that runs `gitwhy check` and turns it on (`hooks.check: true`). It blocks a commit only when a large change has no record, printing the capture command; if gitwhy is missing or the check itself fails, the commit goes ahead. `uninstall-hooks` removes both hooks' blocks.

### Fixed

- Usage errors (unknown command or option, missing argument) exit 1 instead of 2, so exit 2 means only "not a git repo or not initialized".
- `gitwhy init` no longer writes every default into `.gitwhy/config.yml`, which made the project config silently override all user config. It now sets only `schema_version` and lists the defaults as comments.

### Changed

- CI fails when line coverage of `src/gitwhy` drops below 90%.
- Project board type field is named `Work Type`; GitHub reserves `Type`.

[Unreleased]: https://github.com/sabadia/gitwhy/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/sabadia/gitwhy/releases/tag/v0.1.0
