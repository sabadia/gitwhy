"""Shared test fixtures."""

import re
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from whyline.models import Record
from whyline.store import RECORDS_DIRNAME, WHYLINE_DIRNAME, RecordStore

MakeRecord = Callable[..., Record]

SPEC_PATH = Path(__file__).resolve().parents[1] / "docs" / "03-schema-cli-hooks.md"


def doc_yaml_block(heading: str) -> str:
    """Return the first ```yaml block after ``heading`` in docs/03-schema-cli-hooks.md."""
    text = SPEC_PATH.read_text(encoding="utf-8")
    match = re.search(r"```yaml\n(.*?)```", text[text.index(heading) :], re.DOTALL)
    assert match, f"no yaml block after {heading!r}"
    return match.group(1)


def uuid7(n: int) -> UUID:
    """Return a deterministic UUIDv7 whose last 48 bits are ``n``."""
    return UUID(f"01932a7e-5b1c-7c3a-8f21-{n:012x}")


def record_data(n: int = 1, **overrides: Any) -> dict[str, Any]:
    """Return a valid draft record as plain data. ``overrides`` replace top-level keys."""
    created = datetime(2026, 10, 15, 13, 0, n % 60, tzinfo=UTC)
    data: dict[str, Any] = {
        "schema_version": 1,
        "id": str(uuid7(n)),
        "status": "draft",
        "created_at": created,
        "updated_at": created,
        "affirmed_at": None,
        "affirmed_by": None,
        "author": {"kind": "human", "name": "Tester", "tool": None},
        "goal": f"Goal number {n}",
        "constraints": [],
        "rejected": [],
        "assumptions": [],
        "falsifier": "",
        "evidence": [],
        "links": [{"path": "src/app.py", "start_line": 1, "end_line": 10}],
        "adr": None,
        "risks": [],
        "source": {"kind": "flags", "ref": None},
    }
    data.update(overrides)
    return data


@pytest.fixture
def make_record() -> MakeRecord:
    """Build valid ``Record`` objects; pass ``n`` for a distinct id and overrides for fields."""

    def _make(n: int = 1, **overrides: Any) -> Record:
        return Record.model_validate(record_data(n, **overrides))

    return _make


@pytest.fixture
def whyline_dir(tmp_path: Path) -> Path:
    """An initialized ``.whyline`` directory (records dir present) inside ``tmp_path``."""
    path = tmp_path / WHYLINE_DIRNAME
    (path / RECORDS_DIRNAME).mkdir(parents=True)
    return path


@pytest.fixture
def store(whyline_dir: Path) -> RecordStore:
    """A store over an initialized ``.whyline`` directory."""
    return RecordStore(whyline_dir)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """A fresh, empty git repository in ``tmp_path / "repo"`` (no commits)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)  # noqa: S603, S607
    return repo.resolve()
