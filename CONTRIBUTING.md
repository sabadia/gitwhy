# Contributing

The full guide is [docs/contributing.md](docs/contributing.md).

These rules are part of that guide:

- Commits use Conventional Commits.
- Only a human may affirm.
- Do not invent a "why".
- Non-trivial changes in this repo should carry a Intentline record.

Capture a draft with `intentline capture`, mark it with `intentline link` or `--pending`, and commit `.intentline/records` with the change. A draft is fine. Do not affirm a record you did not actually decide. Leave `rejected`, `assumptions`, and `falsifier` empty unless a human supplied them.

```sh
uv sync
uv run ruff check
uv run ruff format --check
uv run mypy
uv run pytest
```
