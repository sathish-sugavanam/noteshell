"""Local SQLite storage for tasks."""

from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3


def database_path() -> Path:
    """Return the platform data-directory path for the task database."""
    data_home = os.environ.get("XDG_DATA_HOME")
    if data_home:
        root = Path(data_home).expanduser()
    else:
        root = Path.home() / ".local" / "share"
    path = root / "task" / "tasks.sqlite3"
    legacy_path = root / "note" / "notes.sqlite3"
    if not path.exists() and legacy_path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        legacy_connection = sqlite3.connect(legacy_path)
        task_connection = sqlite3.connect(path)
        try:
            legacy_connection.backup(task_connection)
        finally:
            task_connection.close()
            legacy_connection.close()
    return path


def now_utc() -> str:
    """Return a sortable UTC timestamp with enough precision for rapid updates."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


@contextmanager
def open_database():
    """Open the task database and ensure its initial schema exists."""
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    connection = sqlite3.connect(path)
    try:
        path.chmod(0o600)
        connection.row_factory = sqlite3.Row
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        if "notes" in tables and "tasks" not in tables:
            connection.execute("ALTER TABLE notes RENAME TO tasks")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
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


def save_task_changes(
    changes: dict[int, tuple[str, str | None, bool, bool]],
    additions: tuple[tuple[str, str | None], ...] = (),
) -> list[int]:
    """Save edits, completion states, soft deletions, and new tasks together."""
    if not changes and not additions:
        return []
    added_ids = []
    with open_database() as connection:
        for task_id, (text, due_at, is_completed, is_deleted) in changes.items():
            timestamp = now_utc()
            cursor = connection.execute(
                "UPDATE tasks SET text = ?, due_at = ?, is_completed = ?, updated_at = ?, deleted_at = ? "
                "WHERE id = ? AND deleted_at IS NULL",
                (
                    text,
                    due_at,
                    int(is_completed),
                    timestamp,
                    timestamp if is_deleted else None,
                    task_id,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"task {task_id} no longer exists")
        for text, due_at in additions:
            timestamp = now_utc()
            cursor = connection.execute(
                "INSERT INTO tasks (text, due_at, created_at, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (text, due_at, timestamp, timestamp),
            )
            added_ids.append(cursor.lastrowid)
    return added_ids


def list_tasks():
    """Return all undeleted tasks, pending first and completed tasks last."""
    with open_database() as connection:
        return connection.execute(
            """
            SELECT id, text, due_at, is_completed, updated_at
            FROM tasks
            WHERE deleted_at IS NULL
            ORDER BY is_completed,
                CASE WHEN is_completed = 0 THEN due_at IS NULL END,
                CASE WHEN is_completed = 0 THEN due_at END,
                CASE WHEN is_completed = 1 THEN updated_at END DESC,
                id
            """
        ).fetchall()
