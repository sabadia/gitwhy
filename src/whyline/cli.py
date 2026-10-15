"""Typer command-line interface for whyline."""

import json
import sys
from dataclasses import replace
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

import typer

# Typer vendors click since 0.26 and exposes no public UsageError or Context base class.
# This is the only place whyline touches the vendored module; uv.lock pins the Typer version,
# and an import failure here fails every CLI test.
from typer._click import Context
from typer._click.exceptions import ClickException, UsageError
from typer.core import TyperGroup

from whyline import __version__
from whyline.affirm import affirm_record, require_human, resolve_affirmer
from whyline.capture import AffirmRequest, CaptureInput, linked_files, prompt_missing
from whyline.capture import capture as run_capture
from whyline.errors import ExitCode, HookConflictError, WhylineError
from whyline.errors import UsageError as WhylineUsageError
from whyline.gitio import repo_root
from whyline.hooks import (
    InstallStatus,
    UninstallStatus,
    apply_pending_trailer,
    install_hook,
    uninstall_hook,
)
from whyline.link import link_amend_head, link_pending
from whyline.models import render_record_json_schema, utc_now
from whyline.recall import RecallResult, parse_location, why_commit, why_line
from whyline.render import filter_records, render_list_line, render_record
from whyline.session import read_session, session_files_in_repo, session_source_ref
from whyline.store import WHYLINE_DIRNAME, RecordStore, initialize

EXIT_CODES_HELP = (
    "[bold]Exit codes:[/bold] 0 ok, 1 usage, 2 not a git repo or not initialized, "
    "3 check failed, 4 corrupt record or config, 5 hook conflict, "
    "6 schema version too new, 7 unsafe git operation, 8 affirm refused, 9 not found."
)


class _ReportedError(ClickException):
    """A ``WhylineError`` shown through click's error output with whyline's exit code."""

    def __init__(self, error: WhylineError) -> None:
        text = error.message if error.hint is None else f"{error.message}\n{error.hint}"
        super().__init__(text)
        self.exit_code = int(error.exit_code)


class WhylineGroup(TyperGroup):
    """Root command group that maps every failure to the exit codes in docs/03 section 3.

    Click exits 2 on usage errors, which would collide with ``no_repo``. This class sets
    exit code 1 on them instead, and turns ``WhylineError`` into a reported error that keeps
    its own exit code. Display and ``sys.exit`` stay with Typer.
    """

    def make_context(
        self,
        info_name: str | None,
        args: list[str],
        parent: Context | None = None,
        **extra: Any,
    ) -> Context:
        try:
            return super().make_context(info_name, args, parent, **extra)
        except UsageError as exc:
            exc.exit_code = ExitCode.USAGE
            raise

    def invoke(self, ctx: Context) -> Any:
        try:
            return super().invoke(ctx)
        except UsageError as exc:
            exc.exit_code = ExitCode.USAGE
            raise
        except WhylineError as exc:
            raise _ReportedError(exc) from exc


# --- shared command plumbing ----------------------------------------------------------------

JsonOption = Annotated[
    bool, typer.Option("--json", help="Print one JSON document on stdout. Logs stay on stderr.")
]
VerboseOption = Annotated[bool, typer.Option("--verbose", "-v", help="Print more detail.")]


def open_store() -> tuple[Path, RecordStore]:
    """Return the repository root containing the cwd, and the record store inside it."""
    root = repo_root(Path.cwd())
    return root, RecordStore(root / WHYLINE_DIRNAME)


def emit_json(data: object) -> None:
    """Write ``data`` to stdout as one indented JSON document."""
    typer.echo(json.dumps(data, indent=2, ensure_ascii=False))


def stdin_is_tty() -> bool:
    """Return True when stdin is an interactive terminal. Tests monkeypatch this."""
    return sys.stdin.isatty()


app = typer.Typer(
    name="whyline",
    cls=WhylineGroup,
    help="Capture why a change exists, and get it back at review and debug time.",
    epilog=EXIT_CODES_HELP,
    no_args_is_help=True,
    rich_markup_mode="rich",
)


@app.callback()
def main() -> None:
    """Git-native intent ledger."""


@app.command()
def version() -> None:
    """Print the installed whyline version."""
    typer.echo(__version__)


@app.command()
def schema() -> None:
    """Print the JSON Schema for a whyline record (draft 2020-12).

    Other tools validate records against this. The same schema is committed as
    schema/record.schema.json.
    """
    typer.echo(render_record_json_schema(), nl=False)


@app.command()
def init(
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Reset .whyline/config.yml to defaults. Records are never touched.",
        ),
    ] = False,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Also list files that were already in place.")
    ] = False,
) -> None:
    """Create .whyline/ at the root of the current git repository.

    Writes config.yml, schema-version, records/.gitkeep, and a .gitignore that keeps the local
    pending file out of commits. Safe to run again: existing files are left alone, and an
    existing config is only replaced with --force.

    Exits 2 outside a git repository, 4 if .whyline/schema-version is unreadable (use --force),
    and 6 if the repository uses a newer schema than this whyline.
    """
    root = repo_root(Path.cwd())
    result = initialize(root, force=force)

    def show(path: Path) -> str:
        return path.relative_to(root).as_posix()

    if not result.changed:
        typer.echo(
            f"Whyline is already initialized in {show(result.whyline_dir)}/. Nothing changed."
        )
    else:
        typer.echo(f"Initialized whyline in {root}:")
        for path in result.created:
            typer.echo(f"  created   {show(path)}")
        for path in result.updated:
            typer.echo(f"  updated   {show(path)}")
    if verbose:
        for path in result.unchanged:
            typer.echo(f"  unchanged {show(path)}")
    if result.changed:
        typer.echo("Commit .whyline/ so the records travel with the repository.")


class StatusFilter(StrEnum):
    """Values accepted by ``whyline list --status``."""

    draft = "draft"
    affirmed = "affirmed"


class AuthorFilter(StrEnum):
    """Values accepted by ``whyline list --author``."""

    human = "human"
    agent = "agent"


@app.command()
def show(
    record_id: Annotated[str, typer.Argument(metavar="ID", help="Record id (a UUID).")],
    json_output: JsonOption = False,
) -> None:
    """Print one record, with a DRAFT or AFFIRMED banner.

    A draft is a claim, not a confirmed reason. Empty fields print as (none).
    --json prints the raw record with no banner.

    Exits 1 for a malformed id, 2 outside an initialized repository, 4 if the record file is
    corrupt, 6 if it uses a newer schema, and 9 if no record has that id.
    """
    _, store = open_store()
    record = store.load(record_id)
    if json_output:
        emit_json(record.model_dump(mode="json"))
    else:
        typer.echo(render_record(record))


@app.command("list")
def list_records(
    status: Annotated[
        StatusFilter | None, typer.Option("--status", help="Only draft or only affirmed records.")
    ] = None,
    path: Annotated[
        str | None,
        typer.Option(
            "--path", metavar="PREFIX", help="Only records linking a path with this prefix."
        ),
    ] = None,
    author: Annotated[
        AuthorFilter | None, typer.Option("--author", help="Only records by a human or an agent.")
    ] = None,
    json_output: JsonOption = False,
) -> None:
    """List records, newest first.

    Files that cannot be read are skipped with a warning on stderr; the rest are still listed.
    --json prints {"records": [...], "skipped": [{"message", "exit_code"}]}.

    Exits 0 even when some files are skipped, 1 for a bad filter value, 2 outside an initialized
    repository, and 6 if the repository uses a newer schema.
    """
    _, store = open_store()
    result = store.list()
    for error in result.errors:
        typer.echo(f"warning: {error}", err=True)
    records = filter_records(
        result.records,
        status=None if status is None else status.value,
        path_prefix=path,
        author_kind=None if author is None else author.value,
    )
    if json_output:
        emit_json(
            {
                "records": [r.model_dump(mode="json") for r in records],
                "skipped": [
                    {"message": str(e), "exit_code": int(e.exit_code)} for e in result.errors
                ],
            }
        )
    elif not records:
        typer.echo("No records.")
    else:
        for record in records:
            typer.echo(render_list_line(record))


def _confirm_empty_fields(fields: list[str]) -> bool:
    typer.echo(f"These fields are empty: {', '.join(fields)}.", err=True)
    return typer.confirm("Affirm anyway?", default=False, err=True)


@app.command()
def affirm(
    record_id: Annotated[str, typer.Argument(metavar="ID", help="Id of the draft to affirm.")],
    by: Annotated[
        str | None,
        typer.Option("--by", help="Who is affirming. Defaults to git config user.name."),
    ] = None,
    yes: Annotated[
        bool,
        typer.Option("--yes", help="Affirm even if narrative fields are empty, without asking."),
    ] = False,
    i_am_human: Annotated[
        bool,
        typer.Option(
            "--i-am-human",
            help="Allow affirming from a non-interactive shell. Only a human may pass this.",
        ),
    ] = False,
    json_output: JsonOption = False,
) -> None:
    """Mark a draft record as affirmed: a human saying "this is the reason".

    Affirming is a human decision. It is refused (exit 8) when stdin is not a terminal,
    unless you pass --i-am-human; you are lying if you pass it and are not a human. Coding
    agents must never affirm. If optional fields are empty, you are asked to confirm;
    --yes skips that question but never skips the human gate. Fields are never filled in.

    Exits 1 on bad input or a declined confirmation, 2 outside an initialized repository,
    4 for a corrupt record, 8 when the human gate refuses, and 9 for an unknown id.
    """
    interactive = stdin_is_tty()
    require_human(interactive=interactive, i_am_human=i_am_human)
    root, store = open_store()
    outcome = affirm_record(
        store,
        record_id,
        by=resolve_affirmer(by, root),
        interactive=interactive,
        i_am_human=i_am_human,
        yes=yes,
        confirm=_confirm_empty_fields,
        now=utc_now(),
    )
    record = outcome.record
    if outcome.empty_fields and not interactive:
        typer.echo(
            f"Warning: affirmed with empty fields: {', '.join(outcome.empty_fields)}.", err=True
        )
    if json_output:
        emit_json(record.model_dump(mode="json"))
    elif outcome.already_affirmed:
        when = record.affirmed_at.isoformat().replace("+00:00", "Z") if record.affirmed_at else "?"
        typer.echo(
            f"{record.id} is already affirmed by {record.affirmed_by} at {when}. Nothing changed."
        )
    else:
        typer.echo(f"Affirmed {record.id} by {record.affirmed_by}.")


ManyOption = list[str] | None


def _ask(question: str, required: bool) -> str:
    """Prompt on stderr so --json output on stdout stays one clean document."""
    if required:
        return str(typer.prompt(question, err=True))
    return str(typer.prompt(question, default="", show_default=False, err=True))


@app.command("capture")
def capture_command(
    goal: Annotated[
        str | None, typer.Option("--goal", help="What this change is for (1-500 characters).")
    ] = None,
    constraint: Annotated[
        ManyOption,
        typer.Option("--constraint", help="A constraint the change must keep. Repeatable."),
    ] = None,
    rejected: Annotated[
        ManyOption,
        typer.Option("--rejected", help="An alternative you considered and rejected. Repeatable."),
    ] = None,
    rejected_reason: Annotated[
        ManyOption,
        typer.Option(
            "--rejected-reason",
            help="Why the --rejected option at the same position was rejected. Repeatable.",
        ),
    ] = None,
    assumption: Annotated[
        ManyOption,
        typer.Option("--assumption", help="An assumption the change relies on. Repeatable."),
    ] = None,
    falsifier: Annotated[
        str, typer.Option("--falsifier", help="What observation would prove this decision wrong.")
    ] = "",
    risk: Annotated[ManyOption, typer.Option("--risk", help="A known risk. Repeatable.")] = None,
    file: Annotated[
        ManyOption,
        typer.Option(
            "--file", help="A file this record explains. Repeatable. Default: staged files."
        ),
    ] = None,
    evidence_test: Annotated[
        str | None, typer.Option("--evidence-test", help="A test that supports the change.")
    ] = None,
    adr: Annotated[str | None, typer.Option("--adr", help="Path to a related ADR.")] = None,
    author_name: Annotated[
        str | None,
        typer.Option(
            "--author-name", help="Author display name. Default: capture.default_author_name."
        ),
    ] = None,
    agent_tool: Annotated[
        str | None,
        typer.Option(
            "--agent-tool", help="Agent tool id (e.g. claude-code). Marks the author as an agent."
        ),
    ] = None,
    pending: Annotated[
        bool,
        typer.Option("--pending", help="Write the id to .whyline/pending for the next commit."),
    ] = False,
    affirm: Annotated[
        bool,
        typer.Option(
            "--affirm",
            help="Affirm the record now (humans only). The same human gate as `whyline affirm`.",
        ),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", help="With --affirm: do not ask about empty fields."),
    ] = False,
    i_am_human: Annotated[
        bool,
        typer.Option(
            "--i-am-human",
            help="With --affirm: allow a non-interactive shell. Only a human may pass this.",
        ),
    ] = False,
    session: Annotated[
        Path | None,
        typer.Option(
            "--session",
            help="Take the goal from a session log's first user message (text or JSON). "
            "Nothing else is read from it.",
        ),
    ] = None,
    json_output: JsonOption = False,
) -> None:
    """Record why a change exists, as a draft.

    Without --goal, on a terminal, capture asks three questions: what the change is for
    (required), what you considered and rejected (optional), and what would prove it wrong
    (optional). A question is skipped when its flag (--rejected, --falsifier) is given.
    Without a terminal, pass --goal and the other fields as flags.

    Every field is stored exactly as given; anything you leave out stays empty. Links default to
    the staged files. Captured records are drafts: a draft is a claim, not a confirmed reason.
    A human may pass --affirm to confirm it in the same step; that is refused (exit 8) from a
    non-interactive shell unless --i-am-human is passed. The affirmer is --author-name, else
    git user.name.

    --session PATH reads a session log (plain text, a JSON message list, or JSONL such as a
    Claude Code transcript). Only the first user message (as the goal) and a top-level "files"
    list are used; --goal and --file override them. Rejected alternatives, assumptions, and the
    falsifier are never taken from session prose: they stay empty unless you pass them. A
    session capture is always a draft, so --session cannot be combined with --affirm.

    Exits 1 for bad input (no --goal and no terminal, an unreadable session, --session with
    --affirm, nothing staged and no --file, a path outside the repository, a declined
    confirmation), 2 outside a git repository or before `whyline init`,
    4 for a corrupt config, 6 if the repository uses a newer schema than this whyline, and 8
    when --affirm is refused by the human gate.
    """
    interactive = stdin_is_tty()
    if affirm:
        require_human(interactive=interactive, i_am_human=i_am_human)
    if session is not None and affirm:
        raise WhylineUsageError(
            "A session capture is always a draft; --session cannot be combined with --affirm.",
            hint="Capture the draft, read it, then run `whyline affirm <id>` yourself.",
        )
    session_path = None if session is None else Path.cwd() / session
    session_facts = None if session_path is None else read_session(session_path)
    if session_facts is not None and goal is None:
        if session_facts.goal is None:
            raise WhylineUsageError(
                f"Session file {session} has no user message or text line to use as the goal.",
                hint='Pass --goal "what this change is for".',
            )
        goal = session_facts.goal
    if goal is None and not interactive:
        raise WhylineUsageError(
            "No goal given, and the interactive questions need a terminal.",
            hint='Pass --goal "what this change is for" (and any other fields as flags).',
        )
    root = repo_root(Path.cwd())
    inp = CaptureInput(
        goal=goal or "",
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
    if session_path is not None and session_facts is not None:
        inp = replace(
            inp,
            files=inp.files or session_files_in_repo(session_facts.files, root),
            source_kind="session",
            source_ref=session_source_ref(session_path, root),
        )
    if goal is None:
        linked_files(inp, root=root, cwd=Path.cwd())
        inp = prompt_missing(inp, _ask)
    request = (
        AffirmRequest(
            by=resolve_affirmer(author_name, root),
            interactive=interactive,
            i_am_human=i_am_human,
            yes=yes,
            confirm=_confirm_empty_fields,
        )
        if affirm
        else None
    )
    result = run_capture(inp, root=root, cwd=Path.cwd(), pending=pending, affirm=request)
    if result.empty_fields and not interactive:
        typer.echo(
            f"Warning: affirmed with empty fields: {', '.join(result.empty_fields)}.", err=True
        )
    shown = result.path.relative_to(root).as_posix()
    if json_output:
        emit_json(
            {
                "id": str(result.record.id),
                "path": shown,
                "pending": result.pending,
                "record": result.record.model_dump(mode="json"),
            }
        )
        return
    if result.record.status == "affirmed":
        typer.echo(f"Captured and affirmed {result.record.id} by {result.record.affirmed_by}")
    else:
        typer.echo(f"Captured draft {result.record.id}")
    typer.echo(f"  {shown}")
    if result.pending:
        typer.echo("  marked pending in .whyline/pending")


@app.command()
def link(
    record_id: Annotated[str, typer.Argument(metavar="ID", help="Id of the record to link.")],
    amend_head: Annotated[
        bool,
        typer.Option(
            "--amend-head",
            help="Add the trailer to the last commit instead (refused if it may be pushed).",
        ),
    ] = False,
    json_output: JsonOption = False,
) -> None:
    """Link a record to a commit with a Whyline-Id trailer.

    By default, writes the id to .whyline/pending; the prepare-commit-msg hook adds the
    trailer to your next commit. With --amend-head, adds the trailer to HEAD now, changing
    only its message (staged changes are not included). That is refused when HEAD is already
    on a remote-tracking branch, is detached, or a merge or rebase is in progress, and when
    HEAD is already linked to a different record.

    Exits 1 for bad input (malformed id, no commit to amend, HEAD linked elsewhere),
    2 outside an initialized repository, 4 for a corrupt record, 7 when amending would be
    unsafe, and 9 for an unknown id.
    """
    root = repo_root(Path.cwd())
    result = link_amend_head(root, record_id) if amend_head else link_pending(root, record_id)
    if json_output:
        emit_json(
            {
                "id": str(result.record_id),
                "pending": result.pending,
                "amended": result.amended,
                "already_linked": result.already_linked,
                "replaced_pending": None
                if result.replaced_pending is None
                else str(result.replaced_pending),
            }
        )
        return
    if result.pending:
        typer.echo(f"Linked {result.record_id} to your next commit (.whyline/pending).")
        if result.replaced_pending is not None:
            typer.echo(f"  replaced the previously pending record {result.replaced_pending}")
    elif result.already_linked:
        typer.echo(f"HEAD already carries Whyline-Id: {result.record_id}. Nothing changed.")
    else:
        sha = result.amended or ""
        typer.echo(f"Amended HEAD ({sha[:12]}) with Whyline-Id: {result.record_id}.")


@app.command("install-hooks")
def install_hooks() -> None:
    """Install the prepare-commit-msg hook that adds the Whyline-Id trailer.

    When .whyline/pending holds an id (see `whyline link` and `capture --pending`), the hook
    adds `Whyline-Id: <id>` to the next commit message and clears pending. It never blocks a
    commit: if whyline is missing or fails, the commit goes ahead without a trailer. Safe to
    run again. Only the lines between the `# whyline-managed` markers belong to whyline.

    A prepare-commit-msg hook that is not whyline's is never overwritten, and nothing is
    written when core.hooksPath is set; in both cases the lines to add yourself are printed on
    stdout and the command exits 5.

    Exits 2 outside a git repository, and 5 when it refuses to write the hook.
    """
    root = repo_root(Path.cwd())
    result = install_hook(root)
    shown = _display_path(result.path, root)
    if result.status is InstallStatus.CREATED:
        typer.echo(f"Installed {result.hook} hook: {shown}")
    elif result.status is InstallStatus.UPDATED:
        typer.echo(f"Updated whyline's block in {shown}")
    elif result.status is InstallStatus.UNCHANGED:
        typer.echo(f"{result.hook} hook already installed: {shown}. Nothing changed.")
    else:
        typer.echo(result.snippet, nl=False)
        if result.status is InstallStatus.HOOKS_PATH:
            raise HookConflictError(
                f"core.hooksPath is set, so whyline did not write into {shown}.",
                hint=f"Add the lines printed above to {shown} (create it with `#!/bin/sh` "
                "if needed, and make it executable).",
            )
        raise HookConflictError(
            f"{shown} already exists and is not managed by whyline; it was left unchanged.",
            hint="Add the lines printed above to it yourself.",
        )


@app.command("uninstall-hooks")
def uninstall_hooks() -> None:
    """Remove whyline's block from the prepare-commit-msg hook.

    Only the lines between the `# whyline-managed` markers are removed; any other lines in
    the hook stay. A hook file left with nothing but a shebang is deleted. Records and
    .whyline/ are not touched.

    Exits 2 outside a git repository.
    """
    root = repo_root(Path.cwd())
    path, status = uninstall_hook(root)
    shown = _display_path(path, root)
    if status is UninstallStatus.REMOVED_FILE:
        typer.echo(f"Removed {shown} (it held only whyline's block).")
    elif status is UninstallStatus.REMOVED_BLOCK:
        typer.echo(f"Removed whyline's block from {shown}; your other lines are unchanged.")
    else:
        typer.echo(f"No whyline hook found in {shown}. Nothing changed.")


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


hook_app = typer.Typer(help="Entry points called by installed git hooks.", hidden=True)
app.add_typer(hook_app, name="hook", hidden=True)


@hook_app.command("prepare-commit-msg")
def hook_prepare_commit_msg(
    message_file: Annotated[Path, typer.Argument()],
    source: Annotated[str | None, typer.Argument()] = None,
    sha: Annotated[str | None, typer.Argument()] = None,
) -> None:
    """Called by git. Adds the pending Whyline-Id trailer. Always exits 0."""
    try:
        root = repo_root(Path.cwd())
        added = apply_pending_trailer(root, root / message_file)
    except Exception as exc:  # a hook must never block a commit: top-level safety boundary
        typer.echo(f"whyline: could not add a Whyline-Id trailer ({exc})", err=True)
        return
    if added is not None:
        typer.echo(f"whyline: added Whyline-Id: {added}", err=True)


@app.command()
def why(
    location: Annotated[
        str | None,
        typer.Argument(metavar="FILE:LINE", help="The line to explain, e.g. src/app.py:40."),
    ] = None,
    commit: Annotated[
        str | None, typer.Option("--commit", help="Explain a commit instead of a line.")
    ] = None,
    all_records: Annotated[
        bool, typer.Option("--all", help="Show every matching record, not just the newest.")
    ] = False,
    json_output: JsonOption = False,
) -> None:
    """Show the records that explain a line (or a commit), newest first.

    Records come from the Whyline-Id trailers of the commits that changed the line (git log
    -L), and from records whose links cover the line. Each starts with AFFIRMED, or with
    "DRAFT — not a confirmed reason": a draft is a claim, not a fact. Output stops at the
    first affirmed record; drafts newer than it are still shown. --all shows everything.
    --json prints {"records": [{"record", "resolved_commits", "via_link"}], ...} with no
    banner text.

    Nothing found is not an error: it prints that no record explains the line and exits 0.
    Exits 1 for bad input (no FILE:LINE and no --commit, or both), 2 outside an initialized
    repository, and 9 for an unknown --commit.
    """
    if (location is None) == (commit is None):
        raise WhylineUsageError(
            "Pass either FILE:LINE or --commit SHA (exactly one).",
            hint="For example: whyline why src/app.py:40",
        )
    root = repo_root(Path.cwd())
    if commit is not None:
        result = why_commit(root, commit)
        query: dict[str, object] = {"commit": commit}
        subject = f"commit {commit}"
    elif location is not None:
        where = parse_location(location, cwd=Path.cwd(), root=root)
        result = why_line(root, where, all_records=all_records)
        query = {"path": where.path, "line": where.line}
        subject = f"{where.path}:{where.line}"
    else:  # pragma: no cover - excluded by the exactly-one check above
        raise WhylineUsageError("Pass either FILE:LINE or --commit SHA.")
    _report_recall_warnings(result)
    if json_output:
        emit_json(
            {
                "query": query,
                "records": [
                    {
                        "record": e.record.model_dump(mode="json"),
                        "resolved_commits": e.commits,
                        "via_link": e.via_link,
                    }
                    for e in result.explanations
                ],
                "missing": [str(record_id) for record_id in result.missing],
                "hidden": result.hidden,
            }
        )
        return
    if not result.explanations:
        prefix = "No commits yet, and no" if result.no_commits else "No"
        typer.echo(f"{prefix} record explains {subject}.")
        return
    blocks = [
        render_record(e.record, commit=e.commits[0][:12] if e.commits else None)
        for e in result.explanations
    ]
    typer.echo("\n\n".join(blocks))
    if result.hidden:
        noun = "record" if result.hidden == 1 else "records"
        typer.echo(f"\n({result.hidden} older {noun} hidden behind the affirmed one; use --all.)")


def _report_recall_warnings(result: RecallResult) -> None:
    if result.shallow:
        typer.echo(
            "warning: this is a shallow clone; older records may be missing "
            "(git fetch --unshallow).",
            err=True,
        )
    for record_id in result.missing:
        typer.echo(f"warning: record missing for id {record_id}", err=True)
    for error in result.skipped:
        typer.echo(f"warning: {error}", err=True)
