"""Typer command-line interface for whyline."""

import json
import sys
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
from whyline.errors import ExitCode, WhylineError
from whyline.errors import UsageError as WhylineUsageError
from whyline.gitio import repo_root
from whyline.models import render_record_json_schema, utc_now
from whyline.render import filter_records, render_list_line, render_record
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

    Exits 1 for bad input (no --goal, nothing staged and no --file, a path outside the
    repository, a declined confirmation), 2 outside a git repository or before `whyline init`,
    4 for a corrupt config, 6 if the repository uses a newer schema than this whyline, and 8
    when --affirm is refused by the human gate.
    """
    interactive = stdin_is_tty()
    if affirm:
        require_human(interactive=interactive, i_am_human=i_am_human)
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
