"""Local stdio MCP server. Optional extra; the core CLI does not import it."""

import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from gitwhy.capture import CaptureInput, capture, resolve_files
from gitwhy.check import run_check
from gitwhy.config import load_config
from gitwhy.errors import GitwhyError, NotFoundError, UsageError
from gitwhy.gitio import repo_root, staged_paths
from gitwhy.link import link_pending
from gitwhy.models import AuthorKind, RecordStatus, render_record_json_schema
from gitwhy.recall import Location, RecallResult, why_commit, why_line
from gitwhy.render import filter_records
from gitwhy.session import read_session, session_files_in_repo, session_source_ref
from gitwhy.store import GITWHY_DIRNAME, RecordStore

_INSTALL_HINT = "uv tool install 'gitwhy[mcp]'"

_INSTRUCTIONS = (
    "Gitwhy stores why a change exists, next to the code. "
    "Draft records are claims, not decisions. Affirmed records are constraints. "
    "Never invent rejected alternatives, assumptions, or a falsifier. "
    "Never affirm a record; affirming is a human action on the gitwhy CLI. "
    "This server is local stdio only and does not use the network."
)


def _recall_payload(result: RecallResult, query: dict[str, Any]) -> dict[str, Any]:
    """CLI ``why --json`` shape, plus the warnings the CLI prints on stderr."""
    warnings: list[str] = []
    if result.shallow:
        warnings.append(
            "this is a shallow clone; older records may be missing (git fetch --unshallow)."
        )
    for record_id in result.missing:
        warnings.append(f"record missing for id {record_id}")
    for error in result.skipped:
        warnings.append(str(error))
    return {
        "query": query,
        "records": [
            {
                "record": explanation.record.model_dump(mode="json"),
                "resolved_commits": explanation.commits,
                "via_link": explanation.via_link,
            }
            for explanation in result.explanations
        ],
        "missing": [str(record_id) for record_id in result.missing],
        "hidden": result.hidden,
        "warnings": warnings,
    }


def _status_filter(status: str | None) -> RecordStatus | None:
    if status is None:
        return None
    if status == "draft":
        return "draft"
    if status == "affirmed":
        return "affirmed"
    raise UsageError(
        f"status must be draft or affirmed, got {status!r}.",
        hint="Omit status to list both.",
    )


def _author_filter(author: str | None) -> AuthorKind | None:
    if author is None:
        return None
    if author == "human":
        return "human"
    if author == "agent":
        return "agent"
    raise UsageError(
        f"author must be human or agent, got {author!r}.",
        hint="Omit author to list both.",
    )


def _review_text() -> str:
    """Prompt body: should this change exist, without invented fields."""
    lines = [
        "Review the current change and answer: should this exist?",
        "Load the Gitwhy records for the changed files (gitwhy_why or gitwhy_list).",
        "An affirmed record is a constraint. A draft is a claim, not a decision.",
        "Do not invent rejected alternatives, assumptions, or a falsifier.",
        "Do not affirm a record.",
    ]
    try:
        root = repo_root(Path.cwd())
        staged = staged_paths(root)
    except GitwhyError as exc:
        lines.append(f"Could not list staged files: {exc}")
        return "\n".join(lines)
    if staged:
        lines.append("Staged files:")
        lines.extend(f"- {path}" for path in staged)
    else:
        lines.append("Nothing is staged.")
    return "\n".join(lines)


def build_server() -> Any:
    """Build the Gitwhy MCP server. Raises ImportError when the mcp extra is missing."""
    from mcp.server import MCPServer
    from mcp.server.mcpserver.exceptions import ResourceError, ResourceNotFoundError, ToolError

    server = MCPServer("gitwhy", instructions=_INSTRUCTIONS)

    def call(action: Any) -> dict[str, Any]:
        try:
            result: dict[str, Any] = action()
        except GitwhyError as exc:
            raise ToolError(str(exc)) from exc
        return result

    def read(action: Any) -> str:
        try:
            text: str = action()
        except NotFoundError as exc:
            raise ResourceNotFoundError(str(exc)) from exc
        except GitwhyError as exc:
            raise ResourceError(str(exc)) from exc
        return text

    @server.tool(name="gitwhy_why")
    def gitwhy_why(
        path: str | None = None,
        line: int | None = None,
        commit: str | None = None,
        all: bool = False,
    ) -> dict[str, Any]:
        """Return the records that explain a line or a commit.

        Pass path and line, or commit, not both. A draft is a claim, not a
        confirmed reason. An affirmed record is a constraint. warnings repeats
        the shallow-clone and missing-record hints. This tool writes nothing.
        """

        def action() -> dict[str, Any]:
            if commit is not None and path is None and line is None:
                root = repo_root(Path.cwd())
                return _recall_payload(why_commit(root, commit), {"commit": commit})
            if path is not None and line is not None and commit is None:
                if line < 1:
                    raise UsageError(f"Line numbers start at 1, got {line}.")
                root = repo_root(Path.cwd())
                (resolved,) = resolve_files([path], cwd=Path.cwd(), root=root)
                return _recall_payload(
                    why_line(root, Location(path=resolved, line=line), all_records=all),
                    {"path": resolved, "line": line},
                )
            if path is not None and line is None and commit is None:
                raise UsageError(
                    "path needs a line.",
                    hint="For example: path src/app.py and line 40.",
                )
            raise UsageError(
                "Pass either path and line, or commit (exactly one).",
                hint="For example: path src/app.py and line 40.",
            )

        return call(action)

    @server.tool(name="gitwhy_capture")
    def gitwhy_capture(
        goal: str | None = None,
        constraint: list[str] | None = None,
        rejected: list[str] | None = None,
        rejected_reason: list[str] | None = None,
        assumption: list[str] | None = None,
        falsifier: str = "",
        risk: list[str] | None = None,
        file: list[str] | None = None,
        evidence_test: str | None = None,
        adr: str | None = None,
        author_name: str | None = None,
        agent_tool: str | None = None,
        session: str | None = None,
        pending: bool = False,
    ) -> dict[str, Any]:
        """Save a draft record. This tool cannot affirm.

        Pass goal, or session (a session log). Only the session's first user
        message becomes the goal, and a top-level files list may be linked.
        Rejected alternatives, assumptions, and the falsifier stay empty unless
        you pass them. Do not invent those fields. Pass agent_tool (for example
        claude-code) when you are an agent; otherwise the author is human.
        pending marks the id for the next commit.
        """

        def action() -> dict[str, Any]:
            session_path: Path | None = None
            session_files: tuple[str, ...] = ()
            if session is not None:
                session_path = Path.cwd() / session
                facts = read_session(session_path)
                session_files = facts.files
                if goal is None:
                    if facts.goal is None:
                        raise UsageError(
                            f"Session file {session} has no user message or text line "
                            "to use as the goal.",
                            hint='Pass goal "what this change is for".',
                        )
                    goal_text = facts.goal
                else:
                    goal_text = goal
            elif goal is None:
                raise UsageError(
                    "No goal given.",
                    hint='Pass goal "what this change is for", or session with a session log.',
                )
            else:
                goal_text = goal
            root = repo_root(Path.cwd())
            captured = CaptureInput(
                goal=goal_text,
                constraints=tuple(constraint or ()),
                rejected=tuple(rejected or ()),
                rejected_reasons=tuple(rejected_reason or ()),
                assumptions=tuple(assumption or ()),
                falsifier=falsifier,
                risks=tuple(risk or ()),
                files=tuple(file or ()),
                evidence_test=evidence_test,
                adr=adr,
                author_name=author_name,
                agent_tool=agent_tool,
            )
            if session_path is not None:
                captured = replace(
                    captured,
                    files=captured.files or session_files_in_repo(session_files, root),
                    source_kind="session",
                    source_ref=session_source_ref(session_path, root),
                )
            result = capture(captured, root=root, cwd=Path.cwd(), pending=pending)
            return {
                "id": str(result.record.id),
                "path": result.path.relative_to(root).as_posix(),
                "pending": result.pending,
                "status": result.record.status,
                "record": result.record.model_dump(mode="json"),
            }

        return call(action)

    @server.tool(name="gitwhy_list")
    def gitwhy_list(
        status: str | None = None,
        path: str | None = None,
        author: str | None = None,
    ) -> dict[str, Any]:
        """List records, newest first.

        status is draft or affirmed. author is human or agent. path keeps
        records whose link starts with that prefix. A draft is a claim. An
        affirmed record is a constraint.
        """

        def action() -> dict[str, Any]:
            status_filter = _status_filter(status)
            author_filter = _author_filter(author)
            root = repo_root(Path.cwd())
            listing = RecordStore(root / GITWHY_DIRNAME).list()
            records = filter_records(
                listing.records,
                status=status_filter,
                path_prefix=path,
                author_kind=author_filter,
            )
            return {
                "records": [record.model_dump(mode="json") for record in records],
                "skipped": [
                    {"message": str(error), "exit_code": int(error.exit_code)}
                    for error in listing.errors
                ],
            }

        return call(action)

    @server.tool(name="gitwhy_show")
    def gitwhy_show(id: str) -> dict[str, Any]:
        """Return one record by id. A draft is a claim, not a confirmed reason."""

        def action() -> dict[str, Any]:
            root = repo_root(Path.cwd())
            record = RecordStore(root / GITWHY_DIRNAME).load(id)
            return record.model_dump(mode="json")

        return call(action)

    @server.tool(name="gitwhy_check")
    def gitwhy_check(range: str | None = None, min_lines: int | None = None) -> dict[str, Any]:
        """Report whether a change needs a record.

        range is a commit range such as main..HEAD; omit it to check the staged
        diff. The result includes ok and verdict. A failing check is that
        result, not a tool error. This tool does not modify the repository.
        """

        def action() -> dict[str, Any]:
            root = repo_root(Path.cwd())
            result = run_check(root, rev_range=range, min_lines=min_lines)
            return {
                "ok": result.ok,
                "verdict": result.verdict.value,
                "changed_lines": result.changed_lines,
                "min_lines": result.min_lines,
                "files": result.counted,
                "ignored": result.ignored,
                "linked_ids": [str(record_id) for record_id in result.linked_ids],
            }

        return call(action)

    @server.tool(name="gitwhy_link")
    def gitwhy_link(id: str) -> dict[str, Any]:
        """Mark a record pending for the next commit. Does not amend HEAD.

        Affirming is not available on this server.
        """

        def action() -> dict[str, Any]:
            root = repo_root(Path.cwd())
            result = link_pending(root, id)
            replaced = None if result.replaced_pending is None else str(result.replaced_pending)
            return {"id": str(result.record_id), "pending": True, "replaced_pending": replaced}

        return call(action)

    @server.resource("gitwhy://schema", mime_type="application/json")
    def schema() -> str:
        """JSON Schema for a Gitwhy record. No repository is required."""
        return render_record_json_schema()

    @server.resource("gitwhy://record/{id}", mime_type="application/json")
    def record(id: str) -> str:
        """One Gitwhy record as JSON. A draft is a claim, not a confirmed reason."""

        def action() -> str:
            root = repo_root(Path.cwd())
            stored = RecordStore(root / GITWHY_DIRNAME).load(id)
            return json.dumps(stored.model_dump(mode="json"), indent=2) + "\n"

        return read(action)

    @server.resource("gitwhy://config", mime_type="application/json")
    def config() -> str:
        """Effective config: defaults, then the user file, then the project file."""

        def action() -> str:
            root = repo_root(Path.cwd())
            return json.dumps(load_config(root).model_dump(mode="json"), indent=2) + "\n"

        return read(action)

    @server.prompt(name="gitwhy-review")
    def gitwhy_review() -> str:
        """Ask whether this change should exist, using records only.

        Do not invent rejected alternatives, assumptions, or a falsifier.
        Do not affirm.
        """
        return _review_text()

    return server


def main() -> None:
    """Run the server on stdio. Exit 1 with an install hint when mcp is missing."""
    try:
        server = build_server()
    except ImportError:
        print(
            f"gitwhy-mcp needs the mcp extra. Install it with: {_INSTALL_HINT}",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
    server.run(transport="stdio")
