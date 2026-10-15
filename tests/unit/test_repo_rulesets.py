"""Guards for the committed repository rulesets and code owners."""

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RULESETS = ROOT / ".github" / "rulesets"
ADMIN_ROLE = {"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}


def _ruleset(name: str) -> dict[str, Any]:
    data = json.loads((RULESETS / f"{name}.json").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _rule_types(ruleset: dict[str, Any]) -> set[str]:
    return {rule["type"] for rule in ruleset["rules"]}


def test_only_admin_role_bypasses_any_ruleset() -> None:
    for path in sorted(RULESETS.glob("*.json")):
        ruleset = _ruleset(path.stem)
        assert ruleset["enforcement"] == "active", path.name
        assert ruleset["bypass_actors"] == [ADMIN_ROLE], path.name


def test_long_lived_branches_block_deletion_and_force_push() -> None:
    ruleset = _ruleset("protected-branches")
    assert set(ruleset["conditions"]["ref_name"]["include"]) == {
        "refs/heads/main",
        "refs/heads/stg",
        "refs/heads/dev",
    }
    assert {"deletion", "non_fast_forward"} <= _rule_types(ruleset)


def test_main_requires_code_owner_approved_pull_request() -> None:
    ruleset = _ruleset("main-review")
    assert ruleset["conditions"]["ref_name"]["include"] == ["refs/heads/main"]
    (rule,) = [r for r in ruleset["rules"] if r["type"] == "pull_request"]
    params = rule["parameters"]
    assert params["required_approving_review_count"] >= 1
    assert params["require_code_owner_review"] is True
    assert params["require_last_push_approval"] is True
    assert params["dismiss_stale_reviews_on_push"] is True
    assert "rebase" not in params["allowed_merge_methods"]


def test_codeowners_covers_every_path() -> None:
    lines = (ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8").splitlines()
    rules = [line.split() for line in lines if line.strip() and not line.startswith("#")]
    assert any(rule[0] == "*" and "@sabadia" in rule[1:] for rule in rules)
