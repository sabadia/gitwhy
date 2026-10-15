"""Interactive ``whyline capture``: the three questions (docs/03 section 4)."""

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from tests.conftest import plain
from whyline.capture import FALSIFIER_QUESTION, GOAL_QUESTION, REJECTED_QUESTION
from whyline.cli import app
from whyline.models import Record
from whyline.store import RecordStore, initialize

runner = CliRunner()


@pytest.fixture
def repo(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    initialize(git_repo)
    (git_repo / "a.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(git_repo), "add", "a.py"], check=True)  # noqa: S603, S607
    monkeypatch.chdir(git_repo)
    monkeypatch.setattr("whyline.cli.stdin_is_tty", lambda: True)
    return git_repo


def _run(answers: str, *args: str) -> Result:
    return runner.invoke(app, ["capture", *args], input=answers)


def _records(repo: Path) -> list[Record]:
    result = RecordStore(repo / ".whyline").list()
    assert result.errors == []
    return [Record.model_validate(r.model_dump()) for r in result.records]


def test_all_three_questions_answered(repo: Path) -> None:
    result = _run("Close invoices daily\nPer-request close\nA customer is charged early\n")
    assert result.exit_code == 0, result.output
    (record,) = _records(repo)
    assert record.goal == "Close invoices daily"
    assert [(r.option, r.reason) for r in record.rejected] == [("Per-request close", "")]
    assert record.falsifier == "A customer is charged early"
    assert record.source.kind == "prompt"
    assert record.status == "draft"
    assert record.assumptions == [] and record.constraints == [] and record.risks == []
    text = plain(result.output)
    assert GOAL_QUESTION in text
    assert "What did you consider and reject?" in text
    assert "What would prove this wrong?" in text


def test_optional_questions_skipped_with_enter_stay_empty(repo: Path) -> None:
    result = _run("Only a goal\n\n\n")
    assert result.exit_code == 0, result.output
    (record,) = _records(repo)
    assert record.goal == "Only a goal"
    assert record.rejected == []
    assert record.falsifier == ""


def test_blank_goal_is_asked_again(repo: Path) -> None:
    result = _run("\n   \nThe real goal\n\n\n")
    assert result.exit_code == 0, result.output
    assert _records(repo)[0].goal == "The real goal"
    assert plain(result.output).count(GOAL_QUESTION) >= 2


def test_flags_skip_their_questions(repo: Path) -> None:
    result = _run("The goal\n", "--rejected", "Do nothing", "--falsifier", "It breaks")
    assert result.exit_code == 0, result.output
    text = plain(result.output)
    assert "What did you consider and reject?" not in text
    assert "What would prove this wrong?" not in text
    (record,) = _records(repo)
    assert record.goal == "The goal"
    assert record.rejected[0].option == "Do nothing"
    assert record.falsifier == "It breaks"
    assert record.source.kind == "prompt"


def test_goal_flag_on_a_terminal_asks_nothing(repo: Path) -> None:
    result = _run("", "--goal", "From a flag")
    assert result.exit_code == 0, result.output
    assert GOAL_QUESTION not in plain(result.output)
    assert _records(repo)[0].source.kind == "flags"


def test_non_tty_without_goal_exits_1_and_writes_nothing(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("whyline.cli.stdin_is_tty", lambda: False)
    result = _run("Would be ignored\n")
    assert result.exit_code == 1
    text = plain(result.output)
    assert "need a terminal" in text
    assert "--goal" in text
    assert _records(repo) == []


def test_eof_mid_prompt_exits_1_and_writes_nothing(repo: Path) -> None:
    result = _run("A goal\n")  # input ends before the second question is answered
    assert result.exit_code == 1, result.output
    assert _records(repo) == []
    assert not (repo / ".whyline" / "pending").exists()


def test_nothing_staged_fails_before_any_question(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    subprocess.run(["git", "-C", str(repo), "reset", "-q"], check=True)  # noqa: S603, S607
    result = _run("Never asked\n\n\n")
    assert result.exit_code == 1
    assert GOAL_QUESTION not in plain(result.output)
    assert "Nothing is staged" in plain(result.output)


def test_goal_over_500_characters_is_a_usage_error(repo: Path) -> None:
    result = _run("x" * 501 + "\n\n\n")
    assert result.exit_code == 1
    assert _records(repo) == []


def test_interactive_with_affirm_and_confirmation(repo: Path) -> None:
    result = _run("The goal\n\n\ny\n", "--affirm", "--author-name", "Ada")
    assert result.exit_code == 0, result.output
    (record,) = _records(repo)
    assert record.status == "affirmed"
    assert record.affirmed_by == "Ada"
    assert record.source.kind == "prompt"


def test_prompts_do_not_pollute_json_stdout(repo: Path) -> None:
    result = _run("The goal\n\n\n", "--json")
    assert result.exit_code == 0, result.output
    # Questions go to stderr. CliRunner echoes the typed answers into stdout (a real terminal
    # shows them on screen, not in the stdout pipe), so parse from the document's start.
    assert GOAL_QUESTION not in result.stdout
    assert GOAL_QUESTION in plain(result.stderr)
    document = json.loads(result.stdout[result.stdout.index("{") :])
    assert document["record"]["source"]["kind"] == "prompt"


def test_question_texts_match_the_spec() -> None:
    assert GOAL_QUESTION == "What is this change for?"
    assert REJECTED_QUESTION.startswith("What did you consider and reject?")
    assert FALSIFIER_QUESTION.startswith("What would prove this wrong?")
