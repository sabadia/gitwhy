"""In-process tests for the stdio MCP server (docs/07 sections 3.2 and 6)."""

import ast
import asyncio
import json
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import pytest
from mcp import Client
from mcp.shared.exceptions import MCPError

from tests.conftest import uuid7
from whyline.adapters.skill import mcp_text
from whyline.mcp import build_server, main
from whyline.store import initialize

_TOOL_NAMES = {
    "whyline_why",
    "whyline_capture",
    "whyline_list",
    "whyline_show",
    "whyline_check",
    "whyline_link",
}


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(  # noqa: S603
        ["git", "-C", str(repo), *args],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _payload(result: Any) -> dict[str, Any]:
    """Return the tool's JSON object, unwrapping a one-field structured envelope."""
    assert result.is_error is False
    data = result.structured_content
    if isinstance(data, dict):
        inner = data.get("result")
        if list(data) == ["result"] and isinstance(inner, dict):
            return inner
        return data
    loaded = json.loads(_text(result))
    assert isinstance(loaded, dict)
    return loaded


def _text(result: Any) -> str:
    return "".join(block.text for block in result.content if getattr(block, "type", None) == "text")


def _resource_text(result: Any) -> str:
    text = getattr(result.contents[0], "text", None)
    assert isinstance(text, str)
    return text


def _prompt_text(result: Any) -> str:
    chunks: list[str] = []
    for message in result.messages:
        content = message.content
        if isinstance(content, str):
            chunks.append(content)
        else:
            text = getattr(content, "text", None)
            if isinstance(text, str):
                chunks.append(text)
    return "\n".join(chunks)


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


@pytest.fixture
def repo(git_repo: Path) -> Path:
    _git(git_repo, "config", "user.name", "Test Human")
    _git(git_repo, "config", "user.email", "test@example.com")
    _git(git_repo, "config", "commit.gpgsign", "false")
    initialize(git_repo)
    return git_repo


def test_tool_list_has_no_affirm() -> None:
    async def body() -> None:
        async with Client(build_server()) as client:
            listed = await client.list_tools()
            names = {tool.name for tool in listed.tools}
            assert names == _TOOL_NAMES
            assert all("affirm" not in name for name in names)
            capture = next(tool for tool in listed.tools if tool.name == "whyline_capture")
            description = capture.description or ""
            assert "draft" in description.lower()
            assert "affirm" in description.lower()
            prompts = await client.list_prompts()
            assert {prompt.name for prompt in prompts.prompts} == {"whyline-review"}
            resources = await client.list_resources()
            uris = {str(resource.uri) for resource in resources.resources}
            assert "whyline://schema" in uris
            assert "whyline://config" in uris
            templates = await client.list_resource_templates()
            patterns = {template.uri_template for template in templates.resource_templates}
            assert "whyline://record/{id}" in patterns
            assert client.instructions is not None
            assert "Never affirm" in client.instructions

    _run(body())


def test_list_outside_a_repo_is_an_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    async def body() -> None:
        async with Client(build_server()) as client:
            result = await client.call_tool("whyline_list", {})
            assert result.is_error is True
            assert "git" in _text(result).lower()

    _run(body())


def test_schema_and_prompt_work_outside_a_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    async def body() -> None:
        async with Client(build_server()) as client:
            schema = await client.read_resource("whyline://schema")
            parsed = json.loads(_resource_text(schema))
            assert parsed["title"] == "Record" or "properties" in parsed
            prompt = await client.get_prompt("whyline-review")
            text = _prompt_text(prompt)
            assert "should this exist?" in text
            assert "Could not list staged files" in text
            with pytest.raises(MCPError, match="git"):
                await client.read_resource("whyline://config")

    _run(body())


def test_capture_then_why(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(repo)
    (repo / "app.py").write_text("print('hello')\n", encoding="utf-8")

    async def body() -> None:
        async with Client(build_server()) as client:
            empty = _payload(await client.call_tool("whyline_list", {}))
            assert empty == {"records": [], "skipped": []}
            captured = _payload(
                await client.call_tool(
                    "whyline_capture",
                    {
                        "goal": "Explain the greeting",
                        "file": ["app.py"],
                        "constraint": ["stay one line"],
                        "agent_tool": "claude-code",
                        "pending": True,
                        "author_name": "Ada",
                    },
                )
            )
            assert captured["status"] == "draft"
            assert captured["pending"] is True
            assert captured["record"]["status"] == "draft"
            assert captured["record"]["author"]["kind"] == "agent"
            assert captured["record"]["author"]["tool"] == "claude-code"
            assert captured["record"]["rejected"] == []
            record_id = captured["id"]
            found = _payload(
                await client.call_tool("whyline_why", {"path": "app.py", "line": 1, "all": True})
            )
            assert found["records"][0]["record"]["id"] == record_id
            assert found["records"][0]["record"]["status"] == "draft"
            assert found["warnings"] == []
            shown = _payload(await client.call_tool("whyline_show", {"id": record_id}))
            assert shown["goal"] == "Explain the greeting"
            checked = _payload(await client.call_tool("whyline_check", {"min_lines": 30}))
            assert checked["ok"] is True
            assert "verdict" in checked
            linked = _payload(await client.call_tool("whyline_link", {"id": record_id}))
            assert linked == {"id": record_id, "pending": True, "replaced_pending": None}
            other = _payload(
                await client.call_tool(
                    "whyline_capture",
                    {"goal": "A second claim", "file": ["app.py"], "agent_tool": "claude-code"},
                )
            )
            replaced = _payload(await client.call_tool("whyline_link", {"id": other["id"]}))
            assert replaced["replaced_pending"] == record_id
            assert replaced["pending"] is True
            record_uri = f"whyline://record/{record_id}"
            body_text = _resource_text(await client.read_resource(record_uri))
            assert json.loads(body_text)["id"] == record_id
            config = json.loads(_resource_text(await client.read_resource("whyline://config")))
            assert config["check"]["min_lines"] == 30
            listed = _payload(
                await client.call_tool(
                    "whyline_list",
                    {"status": "draft", "author": "agent", "path": "app.py"},
                )
            )
            assert {item["id"] for item in listed["records"]} == {record_id, other["id"]}
            prompt = _prompt_text(await client.get_prompt("whyline-review"))
            assert "should this exist?" in prompt
            assert "Nothing is staged." in prompt

    _run(body())


def test_human_author_when_agent_tool_is_omitted(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(repo)

    async def body() -> None:
        async with Client(build_server()) as client:
            captured = _payload(
                await client.call_tool(
                    "whyline_capture",
                    {"goal": "A person wrote this down", "file": ["app.py"]},
                )
            )
            assert captured["record"]["author"]["kind"] == "human"
            assert captured["record"]["author"]["tool"] is None
            assert captured["status"] == "draft"

    _run(body())


def test_capture_without_a_goal_is_an_error(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(repo)

    async def body() -> None:
        async with Client(build_server()) as client:
            result = await client.call_tool("whyline_capture", {})
            assert result.is_error is True
            assert "goal" in _text(result).lower()

    _run(body())


def test_session_capture_does_not_invent_fields(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(repo)
    (repo / "app.py").write_text("x = 1\n", encoding="utf-8")
    session = repo / "session.json"
    session.write_text(
        json.dumps(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Keep the parser strict. I rejected a database because it is heavy. "
                            "What would prove this wrong is a failed benchmark."
                        ),
                    }
                ],
                "files": ["app.py", "/etc/passwd"],
            }
        ),
        encoding="utf-8",
    )

    async def body() -> None:
        async with Client(build_server()) as client:
            captured = _payload(
                await client.call_tool(
                    "whyline_capture",
                    {"session": "session.json", "agent_tool": "claude-code"},
                )
            )
            record = captured["record"]
            assert record["status"] == "draft"
            assert record["rejected"] == []
            assert record["assumptions"] == []
            assert record["falsifier"] == ""
            assert record["source"]["kind"] == "session"
            assert [link["path"] for link in record["links"]] == ["app.py"]
            override = _payload(
                await client.call_tool(
                    "whyline_capture",
                    {
                        "session": "session.json",
                        "goal": "The goal I typed",
                        "file": ["app.py"],
                    },
                )
            )
            assert override["record"]["goal"] == "The goal I typed"
            assert override["record"]["source"]["kind"] == "session"
            missing = await client.call_tool("whyline_capture", {"session": "missing.json"})
            assert missing.is_error is True
            assert "does not exist" in _text(missing)
            empty = repo / "empty.json"
            empty.write_text(
                json.dumps({"messages": [{"role": "assistant", "content": "no user"}]}),
                encoding="utf-8",
            )
            no_goal = await client.call_tool("whyline_capture", {"session": "empty.json"})
            assert no_goal.is_error is True
            assert "goal" in _text(no_goal).lower()

    _run(body())


def test_why_rejects_mixed_targets(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(repo)

    async def body() -> None:
        async with Client(build_server()) as client:
            both = await client.call_tool(
                "whyline_why", {"path": "app.py", "line": 1, "commit": "HEAD"}
            )
            assert both.is_error is True
            assert "exactly one" in _text(both)
            neither = await client.call_tool("whyline_why", {})
            assert neither.is_error is True
            no_line = await client.call_tool("whyline_why", {"path": "app.py"})
            assert no_line.is_error is True
            assert "line" in _text(no_line).lower()
            low = await client.call_tool("whyline_why", {"path": "app.py", "line": 0})
            assert low.is_error is True
            assert "start at 1" in _text(low)
            missing_commit = await client.call_tool("whyline_why", {"commit": "deadbeef"})
            assert missing_commit.is_error is True

    _run(body())


def test_check_failure_is_a_result(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(repo)
    (repo / "app.py").write_text("\n".join(f"line {n}" for n in range(40)) + "\n", encoding="utf-8")
    _git(repo, "add", "app.py")

    async def body() -> None:
        async with Client(build_server()) as client:
            result = await client.call_tool("whyline_check", {})
            assert result.is_error is False
            payload = _payload(result)
            assert payload["ok"] is False
            assert payload["verdict"] == "needs_record"
            assert payload["changed_lines"] >= 40
            bad = await client.call_tool("whyline_check", {"range": "HEAD", "min_lines": -1})
            assert bad.is_error is True

    _run(body())


def test_list_filter_and_show_errors(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(repo)

    async def body() -> None:
        async with Client(build_server()) as client:
            bad_status = await client.call_tool("whyline_list", {"status": "maybe"})
            assert bad_status.is_error is True
            affirmed = _payload(await client.call_tool("whyline_list", {"status": "affirmed"}))
            assert affirmed["records"] == []
            bad_author = await client.call_tool("whyline_list", {"author": "robot"})
            assert bad_author.is_error is True
            humans = _payload(await client.call_tool("whyline_list", {"author": "human"}))
            assert humans["records"] == []
            bad_id = await client.call_tool("whyline_show", {"id": "not-a-uuid"})
            assert bad_id.is_error is True
            missing = await client.call_tool("whyline_show", {"id": str(uuid7(99))})
            assert missing.is_error is True
            with pytest.raises(MCPError, match="No record"):
                await client.read_resource(f"whyline://record/{uuid7(99)}")
            outside = await client.call_tool(
                "whyline_capture",
                {"goal": "nope", "file": ["/etc/passwd"]},
            )
            assert outside.is_error is True
            assert "outside" in _text(outside)

    _run(body())


def test_record_resource_reports_corruption(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(repo)
    (repo / ".whyline" / "records" / f"{uuid7(2)}.yml").write_text("[broken\n", encoding="utf-8")

    async def body() -> None:
        async with Client(build_server()) as client:
            with pytest.raises(MCPError, match="YAML"):
                await client.read_resource(f"whyline://record/{uuid7(2)}")
            listed = _payload(await client.call_tool("whyline_list", {}))
            assert listed["records"] == []
            assert listed["skipped"][0]["exit_code"] == 4

    _run(body())


def test_why_warnings_for_missing_and_skipped(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(repo)
    (repo / "app.py").write_text("a\nb\n", encoding="utf-8")
    _git(repo, "add", "app.py")
    _git(repo, "commit", "-q", "-m", f"start\n\nWhyline-Id: {uuid7(9)}")
    (repo / ".whyline" / "records" / f"{uuid7(2)}.yml").write_text("[broken\n", encoding="utf-8")

    async def body() -> None:
        async with Client(build_server()) as client:
            payload = _payload(await client.call_tool("whyline_why", {"path": "app.py", "line": 1}))
            assert any(str(uuid7(9)) in warning for warning in payload["warnings"])
            assert any("YAML" in warning for warning in payload["warnings"])

    _run(body())


def test_why_warns_on_a_shallow_clone(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (repo / "app.py").write_text("a\n", encoding="utf-8")
    _git(repo, "add", "app.py", ".whyline")
    _git(repo, "commit", "-q", "-m", "one")
    clone = tmp_path / "shallow"
    subprocess.run(  # noqa: S603
        ["git", "clone", "-q", "--depth", "1", f"file://{repo}", str(clone)],  # noqa: S607
        check=True,
        capture_output=True,
    )
    monkeypatch.chdir(clone)

    async def body() -> None:
        async with Client(build_server()) as client:
            payload = _payload(await client.call_tool("whyline_why", {"path": "app.py", "line": 1}))
            assert any("shallow" in warning for warning in payload["warnings"])

    _run(body())


def test_prompt_lists_staged_files(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(repo)
    (repo / "app.py").write_text("a\n", encoding="utf-8")
    _git(repo, "add", "app.py")

    async def body() -> None:
        async with Client(build_server()) as client:
            text = _prompt_text(await client.get_prompt("whyline-review"))
            assert "Staged files:" in text
            assert "app.py" in text

    _run(body())


def test_config_works_before_init(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(git_repo)

    async def body() -> None:
        async with Client(build_server()) as client:
            config = json.loads(_resource_text(await client.read_resource("whyline://config")))
            assert config["schema_version"] == 1
            with pytest.raises(MCPError, match="init"):
                await client.read_resource(f"whyline://record/{uuid7(1)}")

    _run(body())


def test_main_uses_stdio_only(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    class _Server:
        def run(self, transport: str) -> None:
            seen.append(transport)

    monkeypatch.setattr("whyline.mcp.build_server", lambda: _Server())
    main()
    assert seen == ["stdio"]


def test_main_explains_a_missing_extra(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom() -> Any:
        raise ImportError("mcp")

    monkeypatch.setattr("whyline.mcp.build_server", boom)
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    assert "whyline[mcp]" in capsys.readouterr().err


def test_core_install_does_not_depend_on_mcp() -> None:
    root = Path(__file__).resolve().parents[2]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert all("mcp" not in dep for dep in project["project"]["dependencies"])
    assert project["project"]["optional-dependencies"]["mcp"] == ["mcp==2.3.0"]
    assert project["dependency-groups"]["dev"]
    assert "mcp==2.3.0" in project["dependency-groups"]["dev"]
    assert project["project"]["scripts"]["whyline-mcp"] == "whyline.mcp:main"
    source = (root / "src/whyline/cli.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
            assert all(name != "mcp" and not name.startswith("mcp.") for name in names)
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert module != "mcp" and not module.startswith("mcp.")
            assert module != "whyline.mcp"
    server = (root / "src/whyline/mcp.py").read_text(encoding="utf-8")
    assert 'transport="stdio"' in server
    assert "streamable-http" not in server
    assert "whyline[mcp]" in mcp_text()
