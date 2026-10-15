"""Typer command-line interface for whyline."""

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
from whyline.errors import ExitCode, WhylineError
from whyline.gitio import repo_root
from whyline.models import render_record_json_schema
from whyline.store import initialize

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
