# note

A small terminal note manager. Add notes with optional due dates, mark them
complete, and view all notes or filter by status. Notes stay on your computer in
a local SQLite database.

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
note add "Pay electricity bill"
note add "Submit report" --due
note due 1
note done 1
note list
note list p
note list c
note --help
```

The `--due` and `due` commands ask for a date in `YYYY-MM-DD` format and a time
in 24-hour `HH:MM` format. The time prompt starts with an editable `00:00`.
Invalid dates and times are requested again; Ctrl+C cancels without saving. Due
dates use your computer's local timezone. Past deadlines are accepted and shown
as overdue while a note is pending.

`note list` shows pending notes first, ordered by earliest due date and time,
then pending notes without a due date. Completed notes follow, newest completion
first. `note list p` shows only pending notes; `note list c` shows only completed
notes. Completing an already completed note reports that it is already complete.

The database is `~/.local/share/note/notes.sqlite3`, or
`$XDG_DATA_HOME/note/notes.sqlite3` when `XDG_DATA_HOME` is set. It includes
`id`, `text`, `due_at`, `is_completed`, `created_at`, `updated_at`, and
`deleted_at` fields. Deleted notes are reserved for future use; this version
does not include delete commands.
