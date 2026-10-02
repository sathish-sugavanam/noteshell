"""Keyboard-driven terminal view for tasks."""

from datetime import datetime, timedelta, timezone
import sqlite3

from prompt_toolkit.application import Application
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.containers import ConditionalContainer
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import TextArea

from task import storage


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


class InteractiveTasks:
    def __init__(self) -> None:
        self.tasks = [dict(task) for task in storage.list_tasks()]
        for task in self.tasks:
            task["pending_delete"] = False
        self.dirty_ids: set[int] = set()
        self.delete_ids: set[int] = set()
        self.last_added_ids: list[int] = []
        self.selected_id = self.tasks[0]["id"] if self.tasks else None
        self.editing = False
        self.adding_task = False
        self.editing_due = False
        self.original_due_text = ""
        self.status_message = ""
        self.editor = TextArea(
            height=1,
            multiline=False,
            prompt="Task: ",
            wrap_lines=False,
            style="class:editor",
        )
        self.due_editor = TextArea(
            height=1,
            multiline=False,
            prompt="Due:  ",
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
                [("class:title", "Tasks\n"), ("class:divider", "-----")]
            ),
            height=2,
        )
        self.edit_container = ConditionalContainer(
            content=HSplit([self.editor, self.due_editor]),
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

    def ordered_tasks(self) -> list[dict]:
        pending = [task for task in self.tasks if not task["is_completed"]]
        completed = [task for task in self.tasks if task["is_completed"]]
        pending.sort(
            key=lambda task: (
                task["due_at"] is None,
                task["due_at"] or "",
                task["id"],
            )
        )
        completed.sort(
            key=lambda task: (task["updated_at"], task["id"]), reverse=True
        )
        return pending + completed

    def selected_task(self) -> dict | None:
        return next(
            (task for task in self.tasks if task["id"] == self.selected_id),
            None,
        )

    @staticmethod
    def is_overdue(task: dict, now: datetime) -> bool:
        return bool(
            not task["is_completed"]
            and task["due_at"]
            and datetime.fromisoformat(task["due_at"]).astimezone() < now.astimezone()
        )

    @staticmethod
    def due_label(value: str) -> str:
        due = datetime.fromisoformat(value).astimezone()
        today = datetime.now().astimezone().date()
        if due.date() == today:
            date_label = "Today"
        elif due.date() == today + timedelta(days=1):
            date_label = "Tomorrow"
        else:
            day = due.day
            suffix = "th" if 11 <= day % 100 <= 13 else {
                1: "st",
                2: "nd",
                3: "rd",
            }.get(day % 10, "th")
            date_label = f"{day}{suffix} {due:%B %Y}"
        return f"{date_label}, {due:%H:%M}"

    @staticmethod
    def parse_due(value: str) -> str:
        due = datetime.strptime(value, "%Y-%m-%d %H:%M").astimezone()
        return due.astimezone(timezone.utc).isoformat(timespec="seconds")

    @staticmethod
    def edit_due_value(value: str | None) -> str:
        if not value:
            return ""
        return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M")

    def body_entries(self) -> list[tuple[str, str, int | None]]:
        tasks = self.ordered_tasks()
        if not tasks:
            return [
                ("empty", "No tasks yet.", None),
                ("empty", "Press a to add a task.", None),
            ]

        now = datetime.now(timezone.utc)
        overdue = [task for task in tasks if self.is_overdue(task, now)]
        pending = [
            task
            for task in tasks
            if not task["is_completed"] and not self.is_overdue(task, now)
        ]
        completed = [task for task in tasks if task["is_completed"]]
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
            for task in group:
                checked = "x" if task["is_completed"] else " "
                prefix = ">" if task["id"] == self.selected_id else " "
                text = f"{prefix} [{checked}] {task['text']}"
                if task["due_at"]:
                    text += f"  |  Due {self.due_label(task['due_at'])}"
                style = f"row_{kind}"
                if task["pending_delete"]:
                    style += "_deleted"
                if task["id"] == self.selected_id:
                    style += "_selected"
                entries.append((style, text, task["id"]))
        return entries

    def body_text(self):
        entries = self.body_entries()
        selected_line = next(
            (index for index, (_, _, task_id) in enumerate(entries) if task_id == self.selected_id),
            0,
        )
        rows = max(1, self.application.output.get_size().rows - 5 - 2 * int(self.editing))
        start = max(0, min(selected_line - rows // 2, len(entries) - rows))
        visible = entries[start : start + rows]
        fragments = []
        for style, text, _ in visible:
            fragments.append((f"class:{style}", text + "\n"))
        return fragments

    def footer_text(self):
        if self.editing:
            controls = (
                "Tab switch Task/Due  Enter save  Esc cancel\n"
                "Due format: YYYY-MM-DD HH:MM (leave blank to clear)\n"
            )
        else:
            controls = (
                "Up/Down move  Space toggle  Tab edit  a add  d delete\n"
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
        tasks = self.ordered_tasks()
        if not tasks:
            return
        current = next(
            (index for index, task in enumerate(tasks) if task["id"] == self.selected_id),
            0,
        )
        next_index = max(0, min(current + amount, len(tasks) - 1))
        self.selected_id = tasks[next_index]["id"]
        self.status_message = ""
        self.invalidate()

    def toggle_completion(self) -> None:
        task = self.selected_task()
        if task is None:
            self.status_message = "There are no tasks to select."
        elif task["pending_delete"]:
            self.status_message = "Marked for deletion. Press Enter to delete it."
        else:
            task["is_completed"] = int(not task["is_completed"])
            task["updated_at"] = storage.now_utc()
            self.dirty_ids.add(task["id"])
            state = "complete" if task["is_completed"] else "pending"
            self.status_message = f"Marked {state}. Press Enter or q to save."
        self.invalidate()

    def mark_deleted(self) -> None:
        task = self.selected_task()
        if task is None:
            self.status_message = "There are no tasks to delete."
        elif task["pending_delete"]:
            self.status_message = "That task is already marked for deletion."
        else:
            task["pending_delete"] = True
            self.delete_ids.add(task["id"])
            self.status_message = "Marked for deletion. Press Enter to delete; q cancels."
        self.invalidate()

    def begin_edit(self) -> None:
        task = self.selected_task()
        if task is None:
            self.status_message = "There are no tasks to edit."
            self.invalidate()
            return
        self.adding_task = False
        self.editor.text = task["text"]
        self.editor.buffer.cursor_position = len(self.editor.text)
        self.due_editor.text = self.edit_due_value(task["due_at"])
        self.due_editor.buffer.cursor_position = len(self.due_editor.text)
        self.original_due_text = self.due_editor.text
        self.editing_due = False
        self.editing = True
        self.status_message = "Edit the task or its due date."
        self.application.layout.focus(self.editor)
        self.invalidate()

    def begin_add(self) -> None:
        self.adding_task = True
        self.editor.text = ""
        self.editor.buffer.cursor_position = 0
        self.due_editor.text = ""
        self.due_editor.buffer.cursor_position = 0
        self.original_due_text = ""
        self.editing_due = False
        self.editing = True
        self.status_message = "Add a task; a due date is optional."
        self.application.layout.focus(self.editor)
        self.invalidate()

    def cancel_edit(self) -> None:
        self.editing = False
        self.adding_task = False
        self.editing_due = False
        self.status_message = "Edit cancelled."
        self.application.layout.focus(self.body_window)
        self.invalidate()

    def save_changes(
        self,
        *,
        cancel_deletions: bool = False,
        additions: tuple[tuple[str, str | None], ...] = (),
    ) -> bool:
        self.last_added_ids = []
        save_ids = self.dirty_ids | (set() if cancel_deletions else self.delete_ids)
        if not save_ids and not additions:
            return True
        changes = {
            task["id"]: (
                task["text"],
                task["due_at"],
                bool(task["is_completed"]),
                task["id"] in self.delete_ids and not cancel_deletions,
            )
            for task in self.tasks
            if task["id"] in save_ids
        }
        try:
            self.last_added_ids = storage.save_task_changes(changes, additions)
        except (OSError, sqlite3.Error, ValueError) as error:
            self.status_message = f"Could not save tasks: {error}"
            self.invalidate()
            return False
        self.dirty_ids.clear()
        self.delete_ids.clear()
        return True

    def return_to_list(self, preferred_id: int | None, message: str) -> None:
        try:
            self.tasks = [dict(task) for task in storage.list_tasks()]
        except (OSError, sqlite3.Error, ValueError) as error:
            message = f"Saved, but could not refresh the list: {error}"
        else:
            for task in self.tasks:
                task["pending_delete"] = False
            if any(task["id"] == preferred_id for task in self.tasks):
                self.selected_id = preferred_id
            else:
                ordered = self.ordered_tasks()
                self.selected_id = ordered[0]["id"] if ordered else None
        self.editing = False
        self.adding_task = False
        self.status_message = message
        self.application.layout.focus(self.body_window)
        self.invalidate()

    def finish_edit(self) -> None:
        text = self.editor.text.strip()
        if not text:
            self.status_message = "Task text cannot be empty."
            self.invalidate()
            return
        due_text = self.due_editor.text.strip()
        if not self.adding_task and due_text == self.original_due_text:
            task = self.selected_task()
            due_at = task["due_at"] if task is not None else None
        else:
            try:
                due_at = self.parse_due(due_text) if due_text else None
            except ValueError:
                self.status_message = (
                    "Due date must use YYYY-MM-DD HH:MM, "
                    "for example 2027-05-27 13:30."
                )
                self.application.layout.focus(self.due_editor)
                self.editing_due = True
                self.invalidate()
                return
        if self.adding_task:
            if self.save_changes(additions=((text, due_at),)):
                self.return_to_list(
                    self.last_added_ids[-1] if self.last_added_ids else None,
                    "Added task.",
                )
            return
        task = self.selected_task()
        if task is None:
            self.status_message = "That task no longer exists."
            self.cancel_edit()
            return
        if text != task["text"]:
            task["text"] = text
            self.dirty_ids.add(task["id"])
        if due_at != task["due_at"]:
            task["due_at"] = due_at
            self.dirty_ids.add(task["id"])
        if not self.save_changes():
            return
        self.return_to_list(task["id"], "Saved changes.")

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
        def toggle(event) -> None:
            self.toggle_completion()

        @bindings.add("d", filter=list_mode)
        def delete(event) -> None:
            self.mark_deleted()

        @bindings.add("tab", filter=list_mode)
        def edit(event) -> None:
            self.begin_edit()

        @bindings.add("tab", filter=edit_mode)
        def switch_edit_field(event) -> None:
            self.editing_due = not self.editing_due
            target = self.due_editor if self.editing_due else self.editor
            self.application.layout.focus(target)
            self.invalidate()

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
    InteractiveTasks().run()
