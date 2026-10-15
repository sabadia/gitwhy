"""Typer command-line interface for whyline."""

import typer

from whyline import __version__

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
