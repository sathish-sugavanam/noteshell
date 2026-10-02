"""Keyboard-driven terminal view for notes."""

from datetime import datetime, timezone
import sqlite3

from prompt_toolkit.application import Application
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.containers import ConditionalContainer
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import TextArea

from note import storage


STYLE = Style.from_dict(
    {
        "title": "bold",
        "divider": "fg:ansibrightblack",
        "heading_overdue": "fg:ansired bold",
        "row_overdue": "fg:ansired",
        "row_overdue_selected": "fg:ansired bold reverse",
        "row_overdue_deleted": "fg:ansired strike",
        "row_overdue_deleted_selected": "fg:ansired strike bold reverse",
        "heading_pending": "fg:ansiyellow bold",
        "row_pending": "fg:ansiyellow",
        "row_pending_selected": "fg:ansiyellow bold reverse",
        "row_pending_deleted": "fg:ansiyellow strike",
        "row_pending_deleted_selected": "fg:ansiyellow strike bold reverse",
        "heading_completed": "fg:ansibrightblack bold",
        "row_completed": "fg:ansibrightblack",
        "row_completed_selected": "fg:ansibrightblack bold reverse",
        "row_completed_deleted": "fg:ansibrightblack strike",
        "row_completed_deleted_selected": "fg:ansibrightblack strike bold reverse",
        "footer": "fg:ansibrightblack",
        "status": "bold",
        "empty": "fg:ansibrightblack",
        "editor": "fg:ansicyan",
    }
)


class InteractiveNotes:
    def __init__(self) -> None:
        self.notes = [dict(note) for note in storage.list_notes()]
        for note in self.notes:
            note["pending_delete"] = False
        self.dirty_ids: set[int] = set()
        self.delete_ids: set[int] = set()
        self.selected_id = self.notes[0]["id"] if self.notes else None
        self.editing = False
        self.adding_note = False
        self.status_message = ""
        self.editor = TextArea(
            height=1,
            multiline=False,
            prompt="Note: ",
            wrap_lines=False,
            style="class:editor",
        )
        self.body_window = Window(
            content=FormattedTextControl(self.body_text),
            always_hide_cursor=True,
            wrap_lines=False,
        )
        self.header = Window(
            content=FormattedTextControl(
                [("class:title", "Notes\n"), ("class:divider", "-----")]
            ),
            height=2,
        )
        self.edit_container = ConditionalContainer(
            content=self.editor,
            filter=Condition(lambda: self.editing),
        )
        self.footer = Window(
            content=FormattedTextControl(self.footer_text),
            height=3,
        )
        self.key_bindings = self.make_key_bindings()
        root = HSplit([self.header, self.body_window, self.edit_container, self.footer])
        self.application = Application(
            layout=Layout(root, focused_element=self.body_window),
            key_bindings=self.key_bindings,
            style=STYLE,
            full_screen=True,
        )

    def ordered_notes(self) -> list[dict]:
        pending = [note for note in self.notes if not note["is_completed"]]
        completed = [note for note in self.notes if note["is_completed"]]
        pending.sort(
            key=lambda note: (
                note["due_at"] is None,
                note["due_at"] or "",
                note["id"],
            )
        )
        completed.sort(
            key=lambda note: (note["updated_at"], note["id"]), reverse=True
        )
        return pending + completed

    def selected_note(self) -> dict | None:
        return next(
            (note for note in self.notes if note["id"] == self.selected_id),
            None,
        )

    @staticmethod
    def is_overdue(note: dict, now: datetime) -> bool:
        return bool(
            not note["is_completed"]
            and note["due_at"]
            and datetime.fromisoformat(note["due_at"]) < now
        )

    @staticmethod
    def due_label(value: str) -> str:
        return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M")

    def body_entries(self) -> list[tuple[str, str, int | None]]:
        notes = self.ordered_notes()
        if not notes:
            return [
                ("empty", "No notes yet.", None),
                ("empty", "Press a to add a note.", None),
            ]

        now = datetime.now(timezone.utc)
        overdue = [note for note in notes if self.is_overdue(note, now)]
        pending = [
            note
            for note in notes
            if not note["is_completed"] and not self.is_overdue(note, now)
        ]
        completed = [note for note in notes if note["is_completed"]]
        entries: list[tuple[str, str, int | None]] = []

        for title, kind, group in (
            ("Overdue", "overdue", overdue),
            ("Pending", "pending", pending),
            ("Completed", "completed", completed),
        ):
            if not group:
                continue
            entries.append((f"heading_{kind}", title, None))
            entries.append(("divider", "-" * len(title), None))
            for note in group:
                checked = "x" if note["is_completed"] else " "
                prefix = ">" if note["id"] == self.selected_id else " "
                text = f"{prefix} [{note['id']}] [{checked}] {note['text']}"
                if note["due_at"]:
                    text += f"  |  due {self.due_label(note['due_at'])}"
                style = f"row_{kind}"
                if note["pending_delete"]:
                    style += "_deleted"
                if note["id"] == self.selected_id:
                    style += "_selected"
                entries.append((style, text, note["id"]))
        return entries

    def body_text(self):
        entries = self.body_entries()
        selected_line = next(
            (index for index, (_, _, note_id) in enumerate(entries) if note_id == self.selected_id),
            0,
        )
        rows = max(1, self.application.output.get_size().rows - 5 - int(self.editing))
        start = max(0, min(selected_line - rows // 2, len(entries) - rows))
        visible = entries[start : start + rows]
        fragments = []
        for style, text, _ in visible:
            fragments.append((f"class:{style}", text + "\n"))
        return fragments

    def footer_text(self):
        controls = (
            "Up/Down move  Space complete  u reopen  Tab edit  a add  d delete\n"
            "Enter save/exit  q save other changes/exit (cancel deletion)\n"
        )
        status = self.status_message
        if self.dirty_ids or self.delete_ids:
            status = f"Unsaved changes. {status}".strip()
        return [
            ("class:footer", controls),
            ("class:status", status),
        ]

    def invalidate(self) -> None:
        self.application.invalidate()

    def move_selection(self, amount: int) -> None:
        notes = self.ordered_notes()
        if not notes:
            return
        current = next(
            (index for index, note in enumerate(notes) if note["id"] == self.selected_id),
            0,
        )
        next_index = max(0, min(current + amount, len(notes) - 1))
        self.selected_id = notes[next_index]["id"]
        self.status_message = ""
        self.invalidate()

    def mark_completed(self) -> None:
        note = self.selected_note()
        if note is None:
            self.status_message = "There are no notes to select."
        elif note["is_completed"]:
            self.status_message = "That note is already completed."
        elif note["pending_delete"]:
            self.status_message = "Marked for deletion. Press Enter to delete it."
        else:
            note["is_completed"] = 1
            note["updated_at"] = storage.now_utc()
            self.dirty_ids.add(note["id"])
            self.status_message = "Marked complete. Press Enter or q to save."
        self.invalidate()

    def mark_pending(self) -> None:
        note = self.selected_note()
        if note is None:
            self.status_message = "There are no notes to reopen."
        elif not note["is_completed"]:
            self.status_message = "That note is already pending."
        else:
            note["is_completed"] = 0
            note["updated_at"] = storage.now_utc()
            self.dirty_ids.add(note["id"])
            self.status_message = "Marked pending. Press Enter or q to save."
        self.invalidate()

    def mark_deleted(self) -> None:
        note = self.selected_note()
        if note is None:
            self.status_message = "There are no notes to delete."
        elif note["pending_delete"]:
            self.status_message = "That note is already marked for deletion."
        else:
            note["pending_delete"] = True
            self.delete_ids.add(note["id"])
            self.status_message = "Marked for deletion. Press Enter to delete; q cancels."
        self.invalidate()

    def begin_edit(self) -> None:
        note = self.selected_note()
        if note is None:
            self.status_message = "There are no notes to edit."
            self.invalidate()
            return
        self.adding_note = False
        self.editor.text = note["text"]
        self.editor.buffer.cursor_position = len(self.editor.text)
        self.editing = True
        self.status_message = "Enter saves the edit; Esc cancels it."
        self.application.layout.focus(self.editor)
        self.invalidate()

    def begin_add(self) -> None:
        self.adding_note = True
        self.editor.text = ""
        self.editor.buffer.cursor_position = 0
        self.editing = True
        self.status_message = "Enter saves a new note without a due date; Esc cancels."
        self.application.layout.focus(self.editor)
        self.invalidate()

    def cancel_edit(self) -> None:
        self.editing = False
        self.adding_note = False
        self.status_message = "Edit cancelled."
        self.application.layout.focus(self.body_window)
        self.invalidate()

    def save_changes(
        self,
        *,
        cancel_deletions: bool = False,
        additions: tuple[str, ...] = (),
    ) -> bool:
        save_ids = self.dirty_ids | (set() if cancel_deletions else self.delete_ids)
        if not save_ids and not additions:
            return True
        changes = {
            note["id"]: (
                note["text"],
                bool(note["is_completed"]),
                note["id"] in self.delete_ids and not cancel_deletions,
            )
            for note in self.notes
            if note["id"] in save_ids
        }
        try:
            storage.save_note_changes(changes, additions)
        except (OSError, sqlite3.Error, ValueError) as error:
            self.status_message = f"Could not save notes: {error}"
            self.invalidate()
            return False
        self.dirty_ids.clear()
        self.delete_ids.clear()
        return True

    def finish_edit(self) -> None:
        text = self.editor.text.strip()
        if not text:
            self.status_message = "Note text cannot be empty."
            self.invalidate()
            return
        if self.adding_note:
            if self.save_changes(additions=(text,)):
                self.application.exit()
            return
        note = self.selected_note()
        if note is None:
            self.status_message = "That note no longer exists."
            self.cancel_edit()
            return
        if text != note["text"]:
            note["text"] = text
            self.dirty_ids.add(note["id"])
        if not self.save_changes():
            return
        self.application.exit()

    def save_and_exit(self, *, cancel_deletions: bool = False) -> None:
        if self.save_changes(cancel_deletions=cancel_deletions):
            self.application.exit()

    def make_key_bindings(self) -> KeyBindings:
        bindings = KeyBindings()
        list_mode = Condition(lambda: not self.editing)
        edit_mode = Condition(lambda: self.editing)

        @bindings.add("up", filter=list_mode)
        def previous(event) -> None:
            self.move_selection(-1)

        @bindings.add("down", filter=list_mode)
        def following(event) -> None:
            self.move_selection(1)

        @bindings.add(" ", filter=list_mode)
        def complete(event) -> None:
            self.mark_completed()

        @bindings.add("u", filter=list_mode)
        def reopen(event) -> None:
            self.mark_pending()

        @bindings.add("d", filter=list_mode)
        def delete(event) -> None:
            self.mark_deleted()

        @bindings.add("tab", filter=list_mode)
        def edit(event) -> None:
            self.begin_edit()

        @bindings.add("a", filter=list_mode)
        def add(event) -> None:
            self.begin_add()

        @bindings.add("enter")
        def save(event) -> None:
            if self.editing:
                self.finish_edit()
            else:
                self.save_and_exit()

        @bindings.add("escape", filter=edit_mode)
        def cancel(event) -> None:
            self.cancel_edit()

        @bindings.add("q", filter=list_mode)
        def quit_(event) -> None:
            self.save_and_exit(cancel_deletions=True)

        @bindings.add("c-c")
        def interrupt(event) -> None:
            event.app.exit(result=False)

        return bindings

    def run(self) -> None:
        self.application.run()


def run_ui() -> None:
    InteractiveNotes().run()
