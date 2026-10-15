"""v0.1.0 is recorded, and the PyPI job cannot upload on its own."""

import json
from pathlib import Path

from gitwhy import __version__

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "publish.yml"
NETWORK = ("httpx", "requests", "urllib.request")


def _real_publish_at(text: str) -> int:
    """Index of an uploading ``uv publish``, skipping the dry-run line."""
    marker = "run: uv publish"
    start = 0
    while True:
        at = text.find(marker, start)
        if at == -1:
            return -1
        after = text[at + len(marker) : at + len(marker) + 12]
        if after.startswith(" --dry-run") or after.startswith("--dry-run"):
            start = at + len(marker)
            continue
        return at


def unguarded_publish(text: str) -> list[str]:
    """Name how a workflow could upload without an explicit yes.

    A missing dry-run, a missing GITWHY_PUBLISH gate, ``uv publish`` before
    that gate, a missing token, or a literal token are failures.
    """
    gaps: list[str] = []
    if "uv publish --dry-run" not in text:
        gaps.append("no dry-run")
    gate_at = text.find("GITWHY_PUBLISH")
    if gate_at == -1:
        gaps.append("publish is not gated")
    upload_at = _real_publish_at(text)
    if upload_at != -1 and (gate_at == -1 or gate_at > upload_at):
        gaps.append("uv publish appears before its gate")
    if upload_at != -1 and "secrets.UV_PUBLISH_TOKEN" not in text[:upload_at]:
        gaps.append("publish has no token")
    if "pypi-" in text:
        gaps.append("workflow embeds a token")
    return gaps


def test_unguarded_publish_is_rejected() -> None:
    assert unguarded_publish("run: uv publish\n") == [
        "no dry-run",
        "publish is not gated",
        "uv publish appears before its gate",
        "publish has no token",
    ]
    assert unguarded_publish("uv publish --dry-run\nGITWHY_PUBLISH\nrun: uv publish\n") == [
        "publish has no token",
    ]
    literal = (
        "uv publish --dry-run\nGITWHY_PUBLISH\nsecrets.UV_PUBLISH_TOKEN\n"
        "run: uv publish\npypi-secret\n"
    )
    assert "workflow embeds a token" in unguarded_publish(literal)
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
    assert "GITWHY_PUBLISH" in changelog


def test_core_source_does_not_import_a_network_client() -> None:
    offenders: list[str] = []
    for path in (ROOT / "src" / "gitwhy").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for name in NETWORK:
            if name in text:
                offenders.append(f"{path.relative_to(ROOT)} imports {name}")
    assert offenders == []
