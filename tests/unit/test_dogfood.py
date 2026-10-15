"""This repo keeps its own records and the skill it ships (docs/03 section 10)."""

from pathlib import Path

from gitwhy.adapters.skill import MARKER_FILENAME, PROJECT_SKILL_DIRS
from gitwhy.hooks import BEGIN_MARKER, END_MARKER
from gitwhy.store import RecordStore

ROOT = Path(__file__).resolve().parents[2]
PRACTICE = "Non-trivial changes in this repo should carry a Gitwhy record."
GOALS = (
    PRACTICE,
    "Install the skill this repo ships, so an agent working here uses that one text.",
    "Fail when this repo has fewer than three records, a rewritten skill, "
    "or a CONTRIBUTING file that drops the practice.",
)


def dogfood_gaps(
    *,
    record_count: int,
    unreadable: int,
    skill_matches: bool,
    contributing: str,
) -> list[str]:
    """Name what is missing from the dogfood. An empty list means the practice holds.

    Fewer than three records, a record file that does not load, a skill copy that is
    not the shipped text, or a CONTRIBUTING file that drops the practice are failures.
    """
    gaps: list[str] = []
    if record_count < 3:
        gaps.append("fewer than three records")
    if unreadable:
        gaps.append("a record file does not load")
    if not skill_matches:
        gaps.append("installed skill is not the shipped skill")
    if PRACTICE not in contributing:
        gaps.append("CONTRIBUTING does not mention the practice")
    return gaps


def _skill_matches() -> bool:
    src = ROOT / "skills" / "gitwhy"
    try:
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    except OSError:
        return False
    if BEGIN_MARKER not in agents or END_MARKER not in agents:
        return False
    for rel in PROJECT_SKILL_DIRS:
        dest = ROOT / rel
        if not (dest / MARKER_FILENAME).is_file():
            return False
        for path in src.rglob("*"):
            if not path.is_file():
                continue
            copied = dest / path.relative_to(src)
            if not copied.is_file() or copied.read_bytes() != path.read_bytes():
                return False
    return True


def test_dogfood_gaps_name_each_failure() -> None:
    assert dogfood_gaps(
        record_count=2,
        unreadable=0,
        skill_matches=True,
        contributing=PRACTICE,
    ) == ["fewer than three records"]
    assert dogfood_gaps(
        record_count=3,
        unreadable=1,
        skill_matches=True,
        contributing=PRACTICE,
    ) == ["a record file does not load"]
    assert dogfood_gaps(
        record_count=3,
        unreadable=0,
        skill_matches=False,
        contributing=PRACTICE,
    ) == ["installed skill is not the shipped skill"]
    assert dogfood_gaps(
        record_count=3,
        unreadable=0,
        skill_matches=True,
        contributing="Once capture works, maybe write something down.",
    ) == ["CONTRIBUTING does not mention the practice"]


def test_this_repo_dogfoods_drafts_and_the_shipped_skill() -> None:
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    listed = RecordStore(ROOT / ".gitwhy").list()
    gaps = dogfood_gaps(
        record_count=len(listed.records),
        unreadable=len(listed.errors),
        skill_matches=_skill_matches(),
        contributing=contributing,
    )
    assert gaps == []
    by_goal = {record.goal: record for record in listed.records}
    for goal in GOALS:
        record = by_goal[goal]
        assert record.status == "draft"
        assert record.author.kind == "agent"
        assert record.author.tool
        assert record.rejected == []
        assert record.assumptions == []
        assert record.falsifier == ""
        assert record.links
