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


def save_note_changes(
    changes: dict[int, tuple[str, bool, bool]], additions: tuple[str, ...] = ()
) -> None:
    """Save edits, completion states, soft deletions, and new notes together."""
    if not changes and not additions:
        return
    with open_database() as connection:
        for note_id, (text, is_completed, is_deleted) in changes.items():
            timestamp = now_utc()
            cursor = connection.execute(
                "UPDATE notes SET text = ?, is_completed = ?, updated_at = ?, deleted_at = ? "
                "WHERE id = ? AND deleted_at IS NULL",
                (text, int(is_completed), timestamp, timestamp if is_deleted else None, note_id),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"note {note_id} no longer exists")
        for text in additions:
            timestamp = now_utc()
            connection.execute(
                "INSERT INTO notes (text, due_at, created_at, updated_at) "
                "VALUES (?, NULL, ?, ?)",
                (text, timestamp, timestamp),
            )


def list_notes():
    """Return all undeleted notes, pending first and completed notes last."""
    with open_database() as connection:
        return connection.execute(
            """
            SELECT id, text, due_at, is_completed, updated_at
            FROM notes
            WHERE deleted_at IS NULL
            ORDER BY is_completed,
                CASE WHEN is_completed = 0 THEN due_at IS NULL END,
                CASE WHEN is_completed = 0 THEN due_at END,
                CASE WHEN is_completed = 1 THEN updated_at END DESC,
                id
            """
        ).fetchall()
