# Changelog

All notable changes to Whyline are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

### Fixed

- Usage errors (unknown command or option, missing argument) exit 1 instead of 2, so exit 2 means only "not a git repo or not initialized".

### Changed

- Project board type field is named `Work Type`; GitHub reserves `Type`.

[Unreleased]: https://github.com/sabadia/whyline/commits/main
