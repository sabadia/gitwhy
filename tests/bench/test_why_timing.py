"""Time ``why`` on 1,000 records. Opt-in, so CI does not gate on a clock.

Run it with ``WHYLINE_BENCH=1 uv run pytest tests/bench/test_why_timing.py -s``.
"""

import os
import statistics
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.bench.budget import over_budget
from tests.conftest import record_data
from whyline.cli import app
from whyline.models import Record
from whyline.recall import Location, why_line
from whyline.store import RecordStore, initialize

pytestmark = pytest.mark.skipif(
    os.environ.get("WHYLINE_BENCH") != "1",
    reason="local timing, not a CI gate (set WHYLINE_BENCH=1)",
)

runner = CliRunner()
RECORD_COUNT = 1000


def _git(repo: Path, *args: str) -> None:
    subprocess.run(  # noqa: S603
        ["git", "-C", str(repo), *args],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    )


def _median_ms(call: Callable[[], object], rounds: int = 5) -> float:
    samples: list[float] = []
    for _ in range(rounds):
        started = time.perf_counter()
        call()
        samples.append((time.perf_counter() - started) * 1000)
    return statistics.median(samples)


def test_why_on_one_thousand_records_stays_under_the_budget(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _git(git_repo, "config", "user.name", "Test Human")
    _git(git_repo, "config", "user.email", "test@example.com")
    _git(git_repo, "config", "commit.gpgsign", "false")
    initialize(git_repo)
    (git_repo / "src").mkdir()
    (git_repo / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    _git(git_repo, "add", "src/app.py")
    _git(git_repo, "commit", "-q", "-m", "add app")
    store = RecordStore(git_repo / ".whyline")
    for n in range(1, RECORD_COUNT + 1):
        path = "src/app.py" if n == RECORD_COUNT else f"other/f{n}.py"
        store.save(
            Record.model_validate(
                record_data(n, links=[{"path": path, "start_line": 1, "end_line": 1}])
            )
        )
    assert len(store.list().records) == RECORD_COUNT

    where = Location(path="src/app.py", line=1)
    why_line(git_repo, where)
    query_ms = _median_ms(lambda: why_line(git_repo, where))
    found = why_line(git_repo, where)
    assert len(found.explanations) == 1
    assert found.explanations[0].record.goal == f"Goal number {RECORD_COUNT}"

    monkeypatch.chdir(git_repo)
    runner.invoke(app, ["why", "src/app.py:1"])
    command_ms = _median_ms(lambda: runner.invoke(app, ["why", "src/app.py:1"]))

    binary = str(Path(sys.executable).parent / "whyline")
    started = time.perf_counter()
    subprocess.run(  # noqa: S603
        [binary, "why", "src/app.py:1"],
        check=True,
        capture_output=True,
        text=True,
        cwd=git_repo,
    )
    process_ms = (time.perf_counter() - started) * 1000

    report = (
        f"why_line median {query_ms:.2f} ms; "
        f"whyline why in-process median {command_ms:.2f} ms; "
        f"process {process_ms:.2f} ms"
    )
    sys.stderr.write(report + "\n")
    # The budget is the query (docs/02 section 9). Process startup is not part of it:
    # `whyline version` alone is already over 100 ms.
    assert not over_budget(query_ms), report
