"""v0.1.0 is recorded, and the PyPI job cannot upload on its own."""

import json
from pathlib import Path

from whyline import __version__

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "publish.yml"
NETWORK = ("httpx", "requests", "urllib.request")


def unguarded_publish(text: str) -> list[str]:
    """Name how a workflow could upload without an explicit yes.

    A missing dry-run, a missing WHYLINE_PUBLISH gate, or ``uv publish``
    appearing before that gate are failures.
    """
    gaps: list[str] = []
    if "uv publish --dry-run" not in text:
        gaps.append("no dry-run")
    gate_at = text.find("WHYLINE_PUBLISH")
    if gate_at == -1:
        gaps.append("publish is not gated")
    upload_at = text.find("run: uv publish\n")
    if upload_at != -1 and (gate_at == -1 or gate_at > upload_at):
        gaps.append("uv publish appears before its gate")
    return gaps


def test_unguarded_publish_is_rejected() -> None:
    assert unguarded_publish("run: uv publish\n") == [
        "no dry-run",
        "publish is not gated",
        "uv publish appears before its gate",
    ]
    assert unguarded_publish(WORKFLOW.read_text(encoding="utf-8")) == []


def test_version_is_0_1_0_and_the_changelog_has_release_notes() -> None:
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    plugin = json.loads(
        (ROOT / "templates" / "claude-plugin" / ".claude-plugin" / "plugin.json").read_text(
            encoding="utf-8"
        )
    )
    assert 'version = "0.1.0"' in project
    assert __version__ == "0.1.0"
    assert plugin["version"] == "0.1.0"
    assert "## [0.1.0] - 2026-10-15" in changelog
    assert "## [Unreleased]" in changelog
    assert "WHYLINE_PUBLISH" in changelog


def test_core_source_does_not_import_a_network_client() -> None:
    offenders: list[str] = []
    for path in (ROOT / "src" / "whyline").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for name in NETWORK:
            if name in text:
                offenders.append(f"{path.relative_to(ROOT)} imports {name}")
    assert offenders == []
