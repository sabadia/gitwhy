# Changelog

All notable changes to Whyline are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Portable agent skill at `skills/whyline/`: `SKILL.md` tells an agent when to recall a reason and when to capture a draft, and forbids inventing fields or affirming. `scripts/capture.sh` and `scripts/why.sh` call the CLI. `capture.sh` fails if whyline is missing; `why.sh` exits 0 and says there is no record.
- Product specification, architecture, schema contract, roadmap, quality bar, agent integration contract, and Claude Code operating manual.
- Python package skeleton: uv project with hatchling, `src/` layout, `whyline` console script with a `version` command, ruff, mypy strict, and pytest.
- CI on GitHub Actions: ruff check, ruff format --check, mypy, and pytest with coverage on Python 3.12 and 3.13 for pushes to `main` and pull requests.
- Task and Bug issue forms that require acceptance criteria.
- Repository rulesets and CODEOWNERS: only the admin may delete or force-push `main`, `stg`, or `dev`; `main` changes only through code-owner-approved pull requests.
- Record and config models (`whyline.models`) matching the schema v1 contract: UUIDv7 ids, UTC timestamps, draft/affirmed consistency, repo-relative link paths, and a writer/reader split that keeps unknown keys on read.
- Typed error hierarchy with the stable exit codes from the spec (`whyline.errors`).
- Atomic record store (`whyline.store.RecordStore`): save, load, and list under `.whyline/records`; temp file + rename; corrupt files fail cleanly with the path and a next step.
- Schema version gate: a record or a `.whyline/schema-version` newer than this whyline is refused with exit code 6 and an upgrade hint, never guessed at.
- `whyline schema` prints the record JSON Schema (draft 2020-12); the same schema is committed as `schema/record.schema.json` and a test fails if they drift.
- Root `--help` lists the exit codes.
- `whyline init` creates `.whyline/` (config, schema-version, records, and a `.gitignore` for the local pending file) at the repository root. Safe to rerun; `--force` resets only the config and never touches records.
- Layered config loading: built-in defaults < user config (`$WHYLINE_CONFIG_HOME`, `$XDG_CONFIG_HOME/whyline`, or `~/.config/whyline`) < project `.whyline/config.yml`.
- `whyline show <id>` prints one record under a DRAFT or AFFIRMED banner, showing empty fields as `(none)`; `whyline list` lists records newest first with `--status`, `--path`, `--author`, and `--json`, warning on and skipping unreadable files.
- `whyline affirm <id>` marks a draft as affirmed. It is refused (exit 8) from a non-interactive shell unless `--i-am-human` is passed; empty narrative fields need confirmation on a terminal (`--yes` skips it) and are never filled in. `--by` defaults to git `user.name`.
- `whyline capture` (flags mode) writes a draft record from `--goal` and the other docs/03 flags, linked to the staged files or `--file` paths. Fields you leave out stay empty; `--pending` marks the id in `.whyline/pending` for the next commit.
- `whyline capture --affirm` lets a human affirm in the same step, through the same human gate as `whyline affirm` (`--i-am-human`, `--yes`); a refusal or a declined confirmation writes nothing.
- Interactive `whyline capture`: without `--goal` on a terminal it asks what the change is for (required), what was rejected (optional), and what would prove it wrong (optional), skipping questions whose flags were given. Without a terminal it exits 1 and asks for flags.
- `whyline capture --session PATH` takes the goal from a session log's first user message (plain text, a JSON message list, or JSONL such as a Claude Code transcript) and links a top-level `files` list if present. Nothing else is read from the session: rejected alternatives, assumptions, and the falsifier stay empty, session captures are always drafts, and only the file name of a session outside the repository is recorded.
- Git trailer helper (`whyline.gitio`): reads `Whyline-Id` trailers and adds one through `git interpret-trailers`, alongside `Signed-off-by` and other trailers, never replacing an existing link.
- `whyline link <id>` marks a record for the next commit via `.whyline/pending`; `--amend-head` adds the `Whyline-Id` trailer to HEAD's message instead, refusing (exit 7) when HEAD is already on a remote-tracking branch, detached, or mid-merge/rebase, and never replacing an existing link.
- `whyline install-hooks` / `uninstall-hooks`: a `prepare-commit-msg` hook that adds `Whyline-Id` from `.whyline/pending` and clears it. It never blocks a commit, never overwrites a foreign hook (exit 5, prints the lines to add), writes nothing when `core.hooksPath` is set (exit 5), and uninstall removes only whyline's marked block.
- `whyline why FILE:LINE` shows the records that explain a line, newest first, from the `Whyline-Id` trailers of the commits that changed it (`git log -L`) and from records whose links cover it. Each starts with AFFIRMED or `DRAFT — not a confirmed reason`; output stops at the first affirmed record unless `--all`. `--commit SHA` explains a commit; `--json` returns raw records with `resolved_commits`.
- `whyline check [--range A..B] [--min-lines N] [--json]` exits 3 when a change reaches the line threshold (default 30) with no record linked through `.whyline/pending` or a `Whyline-Id` trailer, and prints the capture command. Files matched by `check.ignore` don't count. It never modifies the repository.
- `whyline install-hooks --check` adds an opt-in `pre-commit` hook that runs `whyline check` and turns it on (`hooks.check: true`). It blocks a commit only when a large change has no record, printing the capture command; if whyline is missing or the check itself fails, the commit goes ahead. `uninstall-hooks` removes both hooks' blocks.

### Fixed

- Usage errors (unknown command or option, missing argument) exit 1 instead of 2, so exit 2 means only "not a git repo or not initialized".
- `whyline init` no longer writes every default into `.whyline/config.yml`, which made the project config silently override all user config. It now sets only `schema_version` and lists the defaults as comments.

### Changed

- CI fails when line coverage of `src/whyline` drops below 90%.
- Project board type field is named `Work Type`; GitHub reserves `Type`.

[Unreleased]: https://github.com/sabadia/whyline/commits/main
