"""Local SQLite storage for notes."""

from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3


def database_path() -> Path:
    """Return the platform data-directory path for the note database."""
    data_home = os.environ.get("XDG_DATA_HOME")
    if data_home:
        root = Path(data_home).expanduser()
    else:
        root = Path.home() / ".local" / "share"
    return root / "note" / "notes.sqlite3"


def now_utc() -> str:
    """Return a sortable UTC timestamp with enough precision for rapid updates."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


@contextmanager
def open_database():
    """Open the note database and ensure its initial schema exists."""
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    connection = sqlite3.connect(path)
    try:
        path.chmod(0o600)
        connection.row_factory = sqlite3.Row
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL CHECK (length(trim(text)) > 0),
                due_at TEXT,
                is_completed INTEGER NOT NULL DEFAULT 0 CHECK (is_completed IN (0, 1)),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                deleted_at TEXT
            )
            """
        )
        connection.commit()
        with connection:
            yield connection
    finally:
        connection.close()


def add_note(text: str, due_at: str | None) -> int:
    timestamp = now_utc()
    with open_database() as connection:
        cursor = connection.execute(
            "INSERT INTO notes (text, due_at, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (text, due_at, timestamp, timestamp),
        )
        return cursor.lastrowid


def set_due_date(note_id: int, due_at: str) -> bool:
    with open_database() as connection:
        cursor = connection.execute(
            "UPDATE notes SET due_at = ?, updated_at = ? "
            "WHERE id = ? AND is_completed = 0 AND deleted_at IS NULL",
            (due_at, now_utc(), note_id),
        )
        return cursor.rowcount == 1


def complete_note(note_id: int) -> bool:
    with open_database() as connection:
        cursor = connection.execute(
            "UPDATE notes SET is_completed = 1, updated_at = ? "
            "WHERE id = ? AND is_completed = 0 AND deleted_at IS NULL",
            (now_utc(), note_id),
        )
        return cursor.rowcount == 1


def get_note(note_id: int):
    with open_database() as connection:
        return connection.execute(
            "SELECT id, text, due_at, is_completed FROM notes "
            "WHERE id = ? AND deleted_at IS NULL",
            (note_id,),
        ).fetchone()


def list_notes(status: str):
    """Return notes in the agreed pending/deadline and completed/update order."""
    query = """
        SELECT id, text, due_at, is_completed, updated_at
        FROM notes
        WHERE deleted_at IS NULL
    """
    if status == "p":
        query += " AND is_completed = 0 ORDER BY due_at IS NULL, due_at, id"
    elif status == "c":
        query += " AND is_completed = 1 ORDER BY updated_at DESC, id DESC"
    else:
        query += " ORDER BY is_completed, " \
                 "CASE WHEN is_completed = 0 THEN due_at IS NULL END, " \
                 "CASE WHEN is_completed = 0 THEN due_at END, " \
                 "CASE WHEN is_completed = 1 THEN updated_at END DESC, id"

    with open_database() as connection:
        return connection.execute(query).fetchall()
