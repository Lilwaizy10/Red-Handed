"""Display persisted event metadata and require confirmation before clearing."""

import tkinter as tk
from tkinter import messagebox, ttk


class EventHistoryView(ttk.LabelFrame):
    def __init__(self, parent, recorder):
        super().__init__(parent, text="Event History", padding=8)
        self.recorder = recorder
        self._revision = None
        self.notice = tk.StringVar(master=self)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        columns = ("timestamp", "event", "action", "mode")
        self.table = ttk.Treeview(
            self,
            columns=columns,
            show="headings",
            height=7,
        )

        headings = (
            ("timestamp", "Local time", 170),
            ("event", "Event", 220),
            ("action", "Action", 170),
            ("mode", "Protection mode", 140),
        )
        for name, label, width in headings:
            self.table.heading(name, text=label)
            self.table.column(name, width=width, minwidth=90)

        self.table.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(
            self,
            orient=tk.VERTICAL,
            command=self.table.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.table.configure(yscrollcommand=scrollbar.set)

        controls = ttk.Frame(self)
        controls.grid(row=1, column=0, columnspan=2, sticky="ew", pady=6)

        ttk.Button(
            controls,
            text="Refresh",
            command=lambda: self.refresh(force=True),
        ).pack(side=tk.LEFT)

        ttk.Button(
            controls,
            text="Clear History",
            command=self.clear_history,
        ).pack(side=tk.LEFT, padx=8)

        ttk.Label(
            self,
            textvariable=self.notice,
            wraplength=650,
        ).grid(row=2, column=0, columnspan=2, sticky="ew")

        self.refresh(force=True)

    @staticmethod
    def _format_time(timestamp):
        try:
            return timestamp.astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
        except (OverflowError, OSError, ValueError):
            return timestamp.isoformat(sep=" ")  # local conversion unavailable

    def refresh(self, force=False):
        """Refresh only when the recorder changes, avoiding constant redraws."""
        error = self.recorder.last_error
        if error:
            self.notice.set(error)
        elif force or self._revision != self.recorder.revision:
            self.notice.set("")
        if not force and self._revision == self.recorder.revision:
            return

        # Read the revision before the snapshot. If the writer changes afterward,
        # the next poll notices the newer revision and refreshes again.
        revision = self.recorder.revision
        # Build every row first so a formatting failure can't leave a blank table.
        rows = [(self._format_time(event.timestamp), event.event_type.value,
                 event.action.value,
                 event.protection_mode.value if event.protection_mode else "--")
                for event in self.recorder.events()]

        children = self.table.get_children()
        if children:
            self.table.delete(*children)
        for row in rows:
            self.table.insert("", tk.END, values=row)
        self._revision = revision

    def clear_history(self):
        """Clear persistent storage only after an explicit Yes response."""
        confirmed = messagebox.askyesno(
            "Clear Event History",
            "Delete all saved privacy events? This cannot be undone.",
            parent=self,
        )
        if not confirmed:
            return

        if self.recorder.clear():
            self.refresh(force=True)
            self.notice.set("Event history cleared.")
        else:
            self.notice.set(
                self.recorder.last_error or "Event history could not be cleared."
            )