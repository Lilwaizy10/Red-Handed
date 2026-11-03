"""Compact setup instructions and a border that leaves controls clickable."""

import tkinter as tk
from tkinter import ttk

from red_handed.ui.tutorial_controller import TutorialStep


class TutorialView(ttk.LabelFrame):
    def __init__(self, parent, *, back, next_step, skip, redraw) -> None:
        super().__init__(parent, text="Guided setup", padding=8)
        self.columnconfigure(0, weight=1)
        self.progress = ttk.Label(self, font=("Segoe UI", 10, "bold"))
        self.progress.grid(row=0, column=0, sticky="w", padx=(0, 8))
        controls = self.controls = ttk.Frame(self)
        controls.grid(row=0, column=1, sticky="e")
        self.back_button = ttk.Button(controls, text="Back", command=back, width=6)
        self.back_button.pack(side=tk.LEFT)
        self.next_button = ttk.Button(controls, text="Next", command=next_step, width=11)
        self.next_button.pack(side=tk.LEFT, padx=4)
        self.redraw_button = ttk.Button(controls, text="Draw a replacement", command=redraw)
        self.skip_button = ttk.Button(controls, text="Skip tutorial", command=skip)
        self.skip_button.pack(side=tk.LEFT)
        self.instruction = ttk.Label(self, wraplength=560, justify=tk.LEFT)
        self.instruction.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.bind("<Configure>", self._resize)

    def render(self, step: TutorialStep, index: int, total: int) -> None:
        self.progress.configure(text=f"Step {index + 1} of {total}: {step.title}")
        self.instruction.configure(text=step.instruction)
        self.back_button.configure(state=tk.NORMAL if index and step.back_enabled else tk.DISABLED)
        self.next_button.configure(text=step.next_label, width=max(11, len(step.next_label)),
                                   state=tk.NORMAL if step.next_enabled else tk.DISABLED)
        if step.alternate_label:
            self.redraw_button.configure(text=step.alternate_label)
            self.redraw_button.pack(side=tk.LEFT, before=self.skip_button, padx=(0, 4))
        else:
            self.redraw_button.pack_forget()
        if self.winfo_width() > 24:
            self._wrap(self.winfo_width())

    def _resize(self, event) -> None:
        if event.width > 24:
            self._wrap(event.width)

    def _wrap(self, width) -> None:
        self.instruction.configure(wraplength=width - 24)
        self.progress.configure(wraplength=max(100, width - self.controls.winfo_reqwidth() - 32))


class ControlHighlighter:
    """Four thin borders outside a target, repositioned on layout changes."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.target: tk.Widget | None = None
        self._job: str | None = None
        self._target_bindings: list[tuple[str, str]] = []
        self._borders = [tk.Frame(root, background="#2563eb", takefocus=False) for _ in range(4)]
        self._root_binding = root.bind("<Configure>", self._schedule, add="+")

    def show(self, target: tk.Widget) -> None:
        self.clear()
        self.target = target
        for event in ("<Configure>", "<Map>", "<Unmap>"):
            binding = target.bind(event, self._schedule, add="+")
            self._target_bindings.append((event, binding))
        self._schedule()

    def clear(self) -> None:
        if self._job is not None:
            self.root.after_cancel(self._job)
            self._job = None
        if self.target is not None:
            for event, binding in self._target_bindings:
                self.target.unbind(event, binding)
        self._target_bindings.clear()
        self.target = None
        for border in self._borders:
            border.place_forget()

    def close(self) -> None:
        self.clear()
        if self._root_binding is not None:
            self.root.unbind("<Configure>", self._root_binding)
            self._root_binding = None
        for border in self._borders:
            border.destroy()

    def _schedule(self, event=None) -> None:
        if self.target is None or self._job is not None:
            return
        if event is not None:
            # An ancestor moving also moves the target, without a target Configure event.
            ancestor = self.target
            while ancestor is not None and ancestor is not event.widget:
                ancestor = ancestor.master
            if ancestor is None:
                return
        self._job = self.root.after_idle(self._position)

    def _position(self) -> None:
        self._job = None
        target = self.target
        if target is None:
            return
        if not target.winfo_ismapped():
            for border in self._borders:
                border.place_forget()
            return
        x = target.winfo_rootx() - self.root.winfo_rootx()
        y = target.winfo_rooty() - self.root.winfo_rooty()
        width, height = target.winfo_width(), target.winfo_height()
        rectangles = (
            (x - 3, y - 3, width + 6, 2),
            (x - 3, y + height + 1, width + 6, 2),
            (x - 3, y - 1, 2, height + 2),
            (x + width + 1, y - 1, 2, height + 2),
        )
        for border, (bx, by, bw, bh) in zip(self._borders, rectangles):
            border.place(x=bx, y=by, width=bw, height=bh)
            border.lift()
