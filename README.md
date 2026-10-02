# note

A small keyboard-driven terminal note manager. Create, edit, complete, reopen,
and delete notes from one interactive view. Notes stay on your computer in a
local SQLite database.

## Install

Install [uv](https://docs.astral.sh/uv/) if it is not already available. From
this project folder, install the command for your user:

```sh
uv tool install --editable .
```

If `note` is not found afterward, follow uv's printed instructions to add its
tool directory to your `PATH`.

## Use

```sh
note
```

`note` opens the interactive list. Use Up and Down to select a note, Space to
complete it, `u` to return a completed note to pending, Tab to edit it, and `a`
to add a note. In the editor, Tab switches between the note and its optional due
date. Enter saves and returns to the list; Escape cancels the edit. Due dates use
the local time zone and the `YYYY-MM-DD HH:MM` format (for example,
`2027-05-27 13:30`); leave the field blank to remove a due date. Use `d` to mark
a note for deletion; it is struck through until Enter saves the changes and
deletes it. Enter from the list saves staged changes and exits. `q` saves other
changes and exits, cancelling marked deletions. Ctrl+C exits without saving
staged changes.

The interactive list groups overdue notes in red, other pending notes in yellow,
and completed notes in grey. Each group has a heading and divider. Due dates
appear in deadline order and are shown as “Today” or “Tomorrow” when applicable,
or as a date such as “27th May 2027,” followed by the time.

The database is `~/.local/share/note/notes.sqlite3`, or
`$XDG_DATA_HOME/note/notes.sqlite3` when `XDG_DATA_HOME` is set. It includes
`id`, `text`, `due_at`, `is_completed`, `created_at`, `updated_at`, and
`deleted_at` fields. Deleted notes are hidden from future lists.
