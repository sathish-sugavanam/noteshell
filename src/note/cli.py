"""Single-command entry point for the interactive note manager."""

import sqlite3
import sys

import typer


app = typer.Typer(
    name="note",
    help="Open the interactive note manager.",
    no_args_is_help=False,
    add_completion=False,
)


@app.callback(invoke_without_command=True)
def open_interactive_view(ctx: typer.Context) -> None:
    """Open the keyboard-driven note list."""
    if ctx.invoked_subcommand is not None:
        return
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        typer.echo("The interactive view needs a terminal.", err=True)
        raise typer.Exit(1)

    from note.ui import run_ui

    try:
        run_ui()
    except (OSError, sqlite3.Error, ValueError) as error:
        typer.echo(f"Could not open notes: {error}", err=True)
        raise typer.Exit(1) from error


def main() -> None:
    try:
        app()
    except KeyboardInterrupt:
        typer.echo("\nCancelled.", err=True)
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
