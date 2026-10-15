"""Claude Code Stop hook: print, merge, and draft (docs/03 section 7, docs/05, docs/07)."""

import json
import os
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from tests.conftest import plain
from whyline.adapters.claude import STOP_COMMAND, claude_hook_snippet
from whyline.cli import app
from whyline.models import StoredRecord
from whyline.store import PENDING_FILENAME, RecordStore, initialize

runner = CliRunner()
ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "templates" / "claude-plugin"

_GOAL = "Make the daily close idempotent"
_TEMPTING = (
    "We rejected Redis because of contention. "
    "Assumption: one close per day. "
    "This would be wrong if two closes run concurrently."
)


@pytest.fixture
def repo(git_repo: Path) -> Path:
    initialize(git_repo)
    return git_repo


def _stage(repo: Path, name: str) -> None:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"content of {name}\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "--", name], check=True)  # noqa: S603, S607


def _cli(cwd: Path, monkeypatch: pytest.MonkeyPatch, *args: str, stdin: str = "") -> Result:
    monkeypatch.chdir(cwd)
    return runner.invoke(app, list(args), input=stdin)


def _records(repo: Path) -> list[StoredRecord]:
    store = RecordStore(repo / ".whyline")
    if not store.records_dir.is_dir():
        return []
    listing = store.list()
    assert listing.errors == []
    return listing.records


def _session(tmp_path: Path, body: object, name: str = "session.json") -> Path:
    path = tmp_path / "sessions" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    text = body if isinstance(body, str) else json.dumps(body)
    path.write_text(text, encoding="utf-8")
    return path


def _hook_input(session: Path | None = None, **extra: object) -> str:
    payload: dict[str, object] = {}
    if session is not None:
        payload["transcript_path"] = str(session)
    payload.update(extra)
    return json.dumps(payload)


def _user_session(tmp_path: Path, files: list[str] | None) -> Path:
    body: dict[str, object] = {
        "messages": [
            {"role": "user", "content": _GOAL},
            {"role": "assistant", "content": _TEMPTING},
        ]
    }
    if files is not None:
        body["files"] = files
    return _session(tmp_path, body)


def _settings(repo: Path) -> Path:
    return repo / ".claude" / "settings.json"


# --- print and merge ---------------------------------------------------------------------------


def test_print_is_the_snippet_and_explains_transcript_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _cli(tmp_path, monkeypatch, "adapters", "claude")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == claude_hook_snippet()
    assert "affirm" not in result.stdout
    assert "affirm" not in STOP_COMMAND
    note = result.stderr
    assert "transcript_path" in note
    assert "code.claude.com" in note
    assert "never affirms" in note
    assert not (tmp_path / ".claude").exists()


def test_write_creates_settings_and_a_second_run_keeps_the_bytes(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _cli(repo, monkeypatch, "adapters", "claude", "--write")
    assert first.exit_code == 0, first.output
    assert "Wrote .claude/settings.json." in first.stdout
    assert "transcript_path" in first.stderr
    path = _settings(repo)
    written = path.read_bytes()
    assert json.loads(written) == claude_hook_snippet()
    second = _cli(repo, monkeypatch, "adapters", "claude", "--write")
    assert second.exit_code == 0, second.output
    assert "Nothing changed." in second.stdout
    assert path.read_bytes() == written


def test_write_preserves_other_keys_and_appends_to_an_existing_stop_hook(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _settings(repo)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "permissions": {"allow": ["Bash"]},
                "hooks": {
                    "PreToolUse": [],
                    "Stop": [{"hooks": [{"type": "command", "command": "echo keep"}]}],
                },
            }
        ),
        encoding="utf-8",
    )
    result = _cli(repo, monkeypatch, "adapters", "claude", "--write")
    assert result.exit_code == 0, result.output
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["permissions"] == {"allow": ["Bash"]}
    assert saved["hooks"]["PreToolUse"] == []
    commands = [entry["hooks"][0]["command"] for entry in saved["hooks"]["Stop"]]
    assert commands == ["echo keep", STOP_COMMAND]


def test_write_adds_hooks_when_the_key_is_missing(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _settings(repo)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"permissions": {"allow": ["Read"]}}) + "\n", encoding="utf-8")
    result = _cli(repo, monkeypatch, "adapters", "claude", "--write")
    assert result.exit_code == 0, result.output
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["permissions"] == {"allow": ["Read"]}
    assert saved["hooks"]["Stop"] == claude_hook_snippet()["hooks"]["Stop"]


def test_write_adds_stop_when_hooks_exist_without_it(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _settings(repo)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"hooks": {"PreToolUse": []}}), encoding="utf-8")
    result = _cli(repo, monkeypatch, "adapters", "claude", "--write")
    assert result.exit_code == 0, result.output
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["hooks"]["PreToolUse"] == []
    assert saved["hooks"]["Stop"] == claude_hook_snippet()["hooks"]["Stop"]


def test_write_leaves_an_existing_command_byte_for_byte(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _settings(repo)
    path.parent.mkdir(parents=True)
    original = (
        "{\n"
        '  "hooks": {\n'
        '    "Stop": [\n'
        "      {\n"
        '        "hooks": [\n'
        "          {\n"
        '            "type": "command",\n'
        f'            "command": "{STOP_COMMAND}"\n'
        "          }\n"
        "        ]\n"
        "      }\n"
        "    ]\n"
        "  }\n"
        "}\n"
    )
    path.write_text(original, encoding="utf-8")
    result = _cli(repo, monkeypatch, "adapters", "claude", "--write")
    assert result.exit_code == 0, result.output
    assert "Nothing changed." in result.stdout
    assert path.read_text(encoding="utf-8") == original


@pytest.mark.parametrize(
    "text",
    ["{", "[]", '{"hooks": []}', '{"hooks": {"Stop": {}}}', '{"hooks": {"Stop": "no"}}'],
)
def test_write_refuses_unusable_json_and_leaves_the_file(
    repo: Path, monkeypatch: pytest.MonkeyPatch, text: str
) -> None:
    path = _settings(repo)
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")
    before = path.read_bytes()
    result = _cli(repo, monkeypatch, "adapters", "claude", "--write")
    assert result.exit_code == 4, result.stderr
    assert path.read_bytes() == before
    assert "Fix the file" in plain(result.stderr)


def test_write_outside_a_git_repo_exits_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _cli(tmp_path, monkeypatch, "adapters", "claude", "--write")
    assert result.exit_code == 2, result.stderr
    assert not _settings(tmp_path).exists()


def test_help_names_the_exit_codes() -> None:
    result = runner.invoke(app, ["adapters", "claude", "--help"])
    assert result.exit_code == 0, result.output
    text = plain(result.stdout)
    assert "Exits 2" in text
    assert "and 4 when" in text
    stop = runner.invoke(app, ["adapters", "claude-stop", "--help"])
    assert stop.exit_code == 0, stop.output
    stop_text = plain(stop.stdout)
    assert "Always exits 0" in stop_text
    assert "Never affirms" in stop_text


# --- draft from the session --------------------------------------------------------------------


def test_stop_hook_drafts_one_record_and_ignores_tempting_prose(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _user_session(tmp_path, ["src/app.py"])
    result = _cli(repo, monkeypatch, "adapters", "claude-stop", stdin=_hook_input(session))
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    (record,) = _records(repo)
    assert record.status == "draft"
    assert record.affirmed_at is None
    assert record.goal == _GOAL
    assert record.author.kind == "agent"
    assert record.author.tool == "claude-code"
    assert record.source.kind == "session"
    assert record.source.ref == session.name
    assert record.rejected == []
    assert record.assumptions == []
    assert record.falsifier == ""
    assert [link.path for link in record.links] == ["src/app.py"]
    saved = next((repo / ".whyline" / "records").glob("*.yml")).read_text(encoding="utf-8")
    assert "Redis" not in saved
    assert "contention" not in saved
    assert str(tmp_path) not in saved
    pending = (repo / ".whyline" / PENDING_FILENAME).read_text(encoding="utf-8").strip()
    assert pending == str(record.id)

    again = _cli(repo, monkeypatch, "adapters", "claude-stop", stdin=_hook_input(session))
    assert again.exit_code == 0, again.output
    assert len(_records(repo)) == 1
    assert (repo / ".whyline" / PENDING_FILENAME).read_text(encoding="utf-8").strip() == pending


def test_stop_hook_links_staged_files_when_the_session_lists_none(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stage(repo, "staged.py")
    session = _user_session(tmp_path, None)
    result = _cli(repo, monkeypatch, "adapters", "claude-stop", stdin=_hook_input(session))
    assert result.exit_code == 0, result.output
    (record,) = _records(repo)
    assert [link.path for link in record.links] == ["staged.py"]


def test_stop_hook_writes_nothing_without_files_or_staged_paths(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _user_session(tmp_path, None)
    result = _cli(repo, monkeypatch, "adapters", "claude-stop", stdin=_hook_input(session))
    assert result.exit_code == 0, result.output
    assert _records(repo) == []
    assert not (repo / ".whyline" / PENDING_FILENAME).exists()


def test_stop_hook_ignores_files_outside_the_repo(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path / "outside.py"
    outside.write_text("x\n", encoding="utf-8")
    session = _user_session(tmp_path, [str(outside)])
    result = _cli(repo, monkeypatch, "adapters", "claude-stop", stdin=_hook_input(session))
    assert result.exit_code == 0, result.output
    assert _records(repo) == []
    assert not (repo / ".whyline" / PENDING_FILENAME).exists()


def test_stop_hook_skips_a_session_with_no_user_message(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _session(
        tmp_path,
        {"messages": [{"role": "assistant", "content": _TEMPTING}], "files": ["src/app.py"]},
    )
    result = _cli(repo, monkeypatch, "adapters", "claude-stop", stdin=_hook_input(session))
    assert result.exit_code == 0, result.output
    assert _records(repo) == []


def test_stop_hook_skips_when_stop_hook_active_is_true(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _user_session(tmp_path, ["src/app.py"])
    payload = _hook_input(session, stop_hook_active=True)
    result = _cli(repo, monkeypatch, "adapters", "claude-stop", stdin=payload)
    assert result.exit_code == 0, result.output
    assert _records(repo) == []


@pytest.mark.parametrize(
    "payload",
    [
        "not-json",
        "[]",
        "{}",
        '{"transcript_path": ""}',
        '{"transcript_path": "   "}',
        '{"transcript_path": 12}',
    ],
)
def test_bad_payload_exits_0_and_writes_nothing(
    repo: Path, monkeypatch: pytest.MonkeyPatch, payload: str
) -> None:
    result = _cli(repo, monkeypatch, "adapters", "claude-stop", stdin=payload)
    assert result.exit_code == 0, result.output
    assert _records(repo) == []


def test_missing_session_file_exits_0(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "no-such-session.jsonl"
    result = _cli(repo, monkeypatch, "adapters", "claude-stop", stdin=_hook_input(missing))
    assert result.exit_code == 0, result.output
    assert _records(repo) == []


def test_uninitialized_repo_exits_0(
    git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _user_session(tmp_path, ["src/app.py"])
    result = _cli(git_repo, monkeypatch, "adapters", "claude-stop", stdin=_hook_input(session))
    assert result.exit_code == 0, result.output
    assert not (git_repo / ".whyline").exists()


def test_not_a_git_repo_exits_0(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session = _user_session(tmp_path, ["src/app.py"])
    work = tmp_path / "not-a-repo"
    work.mkdir()
    result = _cli(work, monkeypatch, "adapters", "claude-stop", stdin=_hook_input(session))
    assert result.exit_code == 0, result.output
    assert not (work / ".whyline").exists()


def test_missing_whyline_on_path_exits_0() -> None:
    inner = STOP_COMMAND.removeprefix("sh -c '").removesuffix("'")
    completed = subprocess.run(  # noqa: S603
        ["sh", "-c", inner],  # noqa: S607
        env={**os.environ, "PATH": "/usr/bin:/bin"},
        input="",
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr


def test_claude_stop_exits_0_when_the_hook_itself_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(payload: str, *, cwd: Path | None = None) -> int:
        raise RuntimeError(f"{payload} {cwd}")

    monkeypatch.setattr("whyline.adapters.claude_stop.run_stop_hook", boom)
    result = _cli(tmp_path, monkeypatch, "adapters", "claude-stop", stdin="{}")
    assert result.exit_code == 0


def test_plugin_matches_the_snippet_and_does_not_copy_the_skill() -> None:
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "whyline"
    assert "does not affirm" in manifest["description"]
    assert manifest["author"] == {"name": "Mahamudul Hasan"}
    assert "version" not in manifest
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    assert hooks == claude_hook_snippet()
    assert not (PLUGIN / "skills").exists()
    assert list(PLUGIN.rglob("SKILL.md")) == []
