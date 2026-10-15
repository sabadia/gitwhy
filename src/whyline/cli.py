"""Typer command-line interface for whyline."""

from typing import Any

import typer

# Typer vendors click since 0.26 and exposes no public UsageError or Context base class.
# This is the only place whyline touches the vendored module; uv.lock pins the Typer version,
# and an import failure here fails every CLI test.
from typer._click import Context
from typer._click.exceptions import ClickException, UsageError
from typer.core import TyperGroup

from whyline import __version__
from whyline.errors import ExitCode, WhylineError
from whyline.models import render_record_json_schema

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
