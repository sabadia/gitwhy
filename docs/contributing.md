# Contributing

Intentline is Apache-2.0. Issues and pull requests are welcome at <https://github.com/sabadia/intentline/issues>.

## What a change needs

Non-trivial changes in this repo should carry a Intentline record. Capture a draft with `intentline capture`, mark it with `intentline link` or `--pending`, and commit `.intentline/records` with the change. A draft is fine. Do not affirm a record you did not actually decide. Leave `rejected`, `assumptions`, and `falsifier` empty unless a human supplied them.

Do not invent a "why". Only a human may affirm.

Commits use Conventional Commits, for example `feat:`, `fix:`, `docs:`.

## Set up

```sh
git clone https://github.com/sabadia/intentline.git
cd intentline
uv sync
uv run intentline version
```

Python 3.12 or newer. Tests, lint, and types:

```sh
uv run ruff check
uv run ruff format --check
uv run mypy
uv run pytest
```

Coverage of `src/intentline` fails under 90%. The suite is held at 100%.

## Tests

- Unit tests live in `tests/unit/`.
- Integration tests live in `tests/integration/` and use temporary git repositories.
- The timing check in `tests/bench/` is opt-in. Set `INTENTLINE_BENCH=1` to run it. It is not a CI gate.
- A new behavior needs a test, including one failure path.

`tests/fixtures/schema-examples.md` holds the record and config examples the model tests load. If you change those examples, keep them valid against the Pydantic models.

## Docs and the wiki

User-facing documentation is the Markdown in `docs/`, except `docs/development/`, which is not part of the published tree.

The GitHub wiki is a copy of those public pages. After a docs change lands on `main`:

```sh
python3 scripts/sync_wiki.py
```

That clones `sabadia/intentline.wiki`, rewrites links for the wiki's flat pages, and pushes `master` when you pass `--push`. Review the diff before you push.

## Pull requests

Open a pull request against `main`. Describe what changed and how you tested it. `main` is protected. Do not force-push it.

Do not commit `.env`, tokens, or `docs/development/`.

## Release

Version numbers live in `pyproject.toml`. The `[Unreleased]` section of `CHANGELOG.md` becomes the next release notes. Publishing runs from `.github/workflows/publish.yml` when a version tag is pushed and the repository variable `INTENTLINE_PUBLISH` is `true`. The workflow uses the `UV_PUBLISH_TOKEN` secret.
