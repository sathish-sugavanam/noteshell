"""Command line interface for the note manager."""

from datetime import date, datetime, time, timezone
import re
import sqlite3

import typer
from prompt_toolkit import prompt

from note import storage


app = typer.Typer(
    name="note",
    help="Create and manage notes from your terminal.",
    no_args_is_help=True,
    add_completion=False,
)


def prompt_due_at() -> str:
    while True:
        raw_date = prompt("Date (YYYY-MM-DD): ").strip()
        try:
            if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", raw_date):
                raise ValueError
            due_date = date.fromisoformat(raw_date)
            break
        except ValueError:
            typer.echo("Please enter a valid date as YYYY-MM-DD.", err=True)

    while True:
        raw_time = prompt("Time (HH:MM): ", default="00:00").strip()
        try:
            if not re.fullmatch(r"[0-9]{2}:[0-9]{2}", raw_time):
                raise ValueError
            due_time = time.fromisoformat(raw_time)
            break
        except ValueError:
            typer.echo("Please enter a valid 24-hour time as HH:MM.", err=True)

    local_due = datetime.combine(due_date, due_time).astimezone()
    return local_due.astimezone(timezone.utc).isoformat(timespec="microseconds")


def local_due_label(value: str) -> str:
    due = datetime.fromisoformat(value).astimezone()
    return due.strftime("%Y-%m-%d %H:%M")


def check_id(note_id: int) -> None:
    if note_id < 1:
        raise typer.BadParameter("must be a positive note ID")


@app.command()
def add(
    text: str = typer.Argument(..., help="The note text, in quotes if it has spaces."),
    due: bool = typer.Option(False, "--due", help="Prompt for a due date and time."),
) -> None:
    """Add a note, optionally prompting for its due date and time."""
    text = text.strip()
    if not text:
        raise typer.BadParameter("note text cannot be empty")

    due_at = prompt_due_at() if due else None
    try:
        note_id = storage.add_note(text, due_at)
    except (OSError, sqlite3.Error) as error:
        typer.echo(f"Could not save note: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(f"Added note {note_id}: {text}")


@app.command("list")
def list_command(
    status: str | None = typer.Argument(
        None,
        metavar="[p|c]",
        help="Show pending notes (p), completed notes (c), or both (default).",
    ),
) -> None:
    """List all notes, or filter to pending or completed notes."""
    if status not in (None, "p", "c"):
        raise typer.BadParameter("use 'p' for pending or 'c' for completed")

    try:
        notes = storage.list_notes(status or "all")
    except (OSError, sqlite3.Error) as error:
        typer.echo(f"Could not read notes: {error}", err=True)
        raise typer.Exit(1) from error

    if not notes:
        label = {None: "notes", "p": "pending notes", "c": "completed notes"}[status]
        typer.echo(f"No {label}.")
        return

    now = datetime.now(timezone.utc)
    for note in notes:
        state = "completed" if note["is_completed"] else "pending"
        line = f"{note['id']:>3}  [{state}] {note['text']}"
        if note["due_at"]:
            due = datetime.fromisoformat(note["due_at"])
            line += f"  |  due {local_due_label(note['due_at'])}"
            if not note["is_completed"] and due < now:
                line += " (overdue)"
        typer.echo(line)


@app.command()
def due(note_id: int = typer.Argument(..., min=1, help="The note's ID.")) -> None:
    """Set or change a pending note's due date and time."""
    check_id(note_id)
    try:
        note = storage.get_note(note_id)
        if note is None:
            typer.echo(f"Note {note_id} does not exist.", err=True)
            raise typer.Exit(1)
        if note["is_completed"]:
            typer.echo(f"Note {note_id} is already completed.", err=True)
            raise typer.Exit(1)

        due_at = prompt_due_at()
        storage.set_due_date(note_id, due_at)
    except (OSError, sqlite3.Error) as error:
        typer.echo(f"Could not update note: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(f"Updated due date for note {note_id}: {local_due_label(due_at)}")


@app.command()
def done(note_id: int = typer.Argument(..., min=1, help="The note's ID.")) -> None:
    """Mark a pending note as completed."""
    check_id(note_id)
    try:
        note = storage.get_note(note_id)
        if note is None:
            typer.echo(f"Note {note_id} does not exist.", err=True)
            raise typer.Exit(1)
        if note["is_completed"]:
            typer.echo(f"Note {note_id} is already completed.")
            return
        storage.complete_note(note_id)
    except (OSError, sqlite3.Error) as error:
        typer.echo(f"Could not complete note: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(f"Completed note {note_id}: {note['text']}")


def main() -> None:
    try:
        app()
    except KeyboardInterrupt:
        typer.echo("\nCancelled.", err=True)
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
