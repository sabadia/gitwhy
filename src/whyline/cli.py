"""Typer command-line interface for whyline."""

import typer

from whyline import __version__
from whyline.models import render_record_json_schema

app = typer.Typer(
    name="whyline",
    help="Capture why a change exists, and get it back at review and debug time.",
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
