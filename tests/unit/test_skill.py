"""The portable agent skill is one file agents can load without forking it."""

import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = ROOT / "skills" / "gitwhy"
SKILL = SKILL_DIR / "SKILL.md"
CAPTURE = SKILL_DIR / "scripts" / "capture.sh"
WHY = SKILL_DIR / "scripts" / "why.sh"

WHEN_TO_USE = (
    "why did we do this",
    "record the reason",
    "intent",
    "decision",
    "gitwhy",
)


def _frontmatter(text: str) -> tuple[dict[str, object], str]:
    assert text.startswith("---\n"), "SKILL.md must open with YAML frontmatter"
    _, raw, body = text.split("---", 2)
    loaded = yaml.safe_load(raw)
    assert isinstance(loaded, dict)
    return loaded, body


def test_skill_frontmatter_says_when_to_use_it() -> None:
    meta, body = _frontmatter(SKILL.read_text(encoding="utf-8"))
    assert meta["name"] == "gitwhy"
    assert set(meta) <= {"name", "description", "license"}
    description = meta["description"]
    assert isinstance(description, str)
    assert 1 <= len(description) <= 1024
    folded = " ".join(description.split()).lower()
    for phrase in WHEN_TO_USE:
        assert phrase in folded
    lowered = body.lower()
    assert "do not invent" in lowered
    assert "gitwhy affirm" in lowered
    assert "draft" in lowered
    assert "constraint" in lowered


def test_references_hold_the_short_schema_note() -> None:
    schema = (SKILL_DIR / "references" / "schema.md").read_text(encoding="utf-8")
    assert "docs/03-schema-cli-hooks.md" in schema
    for field in ("goal", "rejected", "assumptions", "falsifier", "status"):
        assert field in schema
    agents = (SKILL_DIR / "references" / "agents.md").read_text(encoding="utf-8")
    assert ".claude/skills/gitwhy/SKILL.md" in agents
    assert ".agents/skills/gitwhy/SKILL.md" in agents
    assert "do not fork" in agents.lower()


def test_scripts_call_the_cli_and_are_executable() -> None:
    capture = CAPTURE.read_text(encoding="utf-8")
    why = WHY.read_text(encoding="utf-8")
    assert "gitwhy capture" in capture
    assert "gitwhy why" in why
    assert os.access(CAPTURE, os.X_OK)
    assert os.access(WHY, os.X_OK)


def test_capture_sh_fails_when_gitwhy_is_missing() -> None:
    completed = subprocess.run(  # noqa: S603
        ["sh", str(CAPTURE), "--goal", "unused"],  # noqa: S607
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": "/usr/bin:/bin"},
    )
    assert completed.returncode != 0
    assert "gitwhy is not on PATH" in completed.stderr


def test_why_sh_reports_no_record_when_gitwhy_is_missing() -> None:
    completed = subprocess.run(  # noqa: S603
        ["sh", str(WHY), "src/app.py:1"],  # noqa: S607
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": "/usr/bin:/bin"},
    )
    assert completed.returncode == 0
    assert "No record" in completed.stdout


def test_scripts_forward_arguments_to_gitwhy(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "log"
    fake = bin_dir / "gitwhy"
    fake.write_text(
        '#!/bin/sh\nprintf \'%s\\n\' "$0" "$@" > "$GITWHY_FAKE_LOG"\n',
        encoding="utf-8",
    )
    fake.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin",
        "GITWHY_FAKE_LOG": str(log),
    }
    capture = subprocess.run(  # noqa: S603
        ["sh", str(CAPTURE), "--goal", "close invoices", "--pending"],  # noqa: S607
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert capture.returncode == 0, capture.stderr
    assert log.read_text(encoding="utf-8").splitlines()[1:] == [
        "capture",
        "--goal",
        "close invoices",
        "--pending",
    ]
    why = subprocess.run(  # noqa: S603
        ["sh", str(WHY), "src/app.py:40"],  # noqa: S607
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert why.returncode == 0, why.stderr
    assert log.read_text(encoding="utf-8").splitlines()[1:] == ["why", "src/app.py:40"]
