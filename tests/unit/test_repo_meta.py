"""Guards for repository metadata that contributors rely on."""

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = sorted((ROOT / ".github" / "ISSUE_TEMPLATE").glob("*.yml"))
ISSUE_FORMS = [t for t in TEMPLATES if t.name != "config.yml"]


def _load(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{path} is not a YAML mapping"
    return data


def test_issue_forms_exist() -> None:
    assert ISSUE_FORMS, "no issue forms found under .github/ISSUE_TEMPLATE"


@pytest.mark.parametrize("form", ISSUE_FORMS, ids=lambda p: p.name)
def test_issue_form_requires_acceptance_criteria(form: Path) -> None:
    body = _load(form)["body"]
    fields = [item for item in body if item.get("id") == "acceptance"]
    assert len(fields) == 1, f"{form.name} has no acceptance criteria field"
    assert fields[0]["validations"]["required"] is True


def test_blank_issues_disabled() -> None:
    config = _load(ROOT / ".github" / "ISSUE_TEMPLATE" / "config.yml")
    assert config["blank_issues_enabled"] is False


def test_changelog_has_unreleased_section() -> None:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "keepachangelog.com" in text
    assert "## [Unreleased]" in text
    assert "[Unreleased]: https://github.com/sabadia/whyline/" in text


def test_contributing_states_the_rules() -> None:
    text = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "Conventional Commits" in text
    assert "Only a human may affirm" in text
    assert 'Do not invent a "why"' in text
