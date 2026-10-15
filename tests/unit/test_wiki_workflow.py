"""The wiki job publishes docs from main and does not force-push."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "wiki.yml"


def wiki_gaps(text: str) -> list[str]:
    """Name how a wiki workflow could publish the wrong tree or rewrite history."""
    gaps: list[str] = []
    if "docs/**" not in text:
        gaps.append("does not watch docs")
    if "branches: [main]" not in text:
        gaps.append("not limited to main")
    if "contents: write" not in text:
        gaps.append("cannot push")
    if "scripts/sync_wiki.py" not in text:
        gaps.append("does not sync")
    if "pull_request:" in text:
        gaps.append("runs on pull requests")
    if "--force" in text:
        gaps.append("force-pushes")
    if "pypi-" in text:
        gaps.append("embeds a token")
    return gaps


def test_an_open_wiki_job_is_rejected() -> None:
    opened = "on:\n  pull_request:\n  push:\n    branches: [main]\n  run: git push --force\n"
    assert wiki_gaps(opened) == [
        "does not watch docs",
        "cannot push",
        "does not sync",
        "runs on pull requests",
        "force-pushes",
    ]
    assert wiki_gaps(WORKFLOW.read_text(encoding="utf-8")) == []
