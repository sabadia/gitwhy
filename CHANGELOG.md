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

### Changed

- Project board type field is named `Work Type`; GitHub reserves `Type`.

[Unreleased]: https://github.com/sabadia/whyline/commits/main
