# TODO [FR1, FR12]: Present monitoring controls and system status.

"""Tkinter dashboard: status, monitoring controls and a camera preview."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from red_handed.core.system_state import CameraStatus, MonitoringStatus, SystemState


class PreviewCanvas(tk.Canvas):
    """Camera image, or a text message while there is no image."""

    def __init__(self, parent) -> None:
        super().__init__(parent, width=640, height=320, bg="#111827", highlightthickness=0)
        self._photo = None
        self._message = "Camera preview is inactive"
        self.bind("<Configure>", lambda _: self._draw())

    def show_image(self, photo) -> None:
        self._photo = photo
        self._draw()

    def clear(self, text: str) -> None:
        self._photo = None
        self._message = text
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        cx, cy = self.winfo_width() / 2, self.winfo_height() / 2
        if self._photo is None:
            self.create_text(cx, cy, text=self._message, fill="#e5e7eb")
            return
        self.create_image(cx, cy, image=self._photo)


class MainWindow:
    """Present status and monitoring controls."""

    def __init__(self, root: tk.Tk, state: SystemState,
                 on_start: Callable[[], None] | None = None,
                 on_stop: Callable[[], None] | None = None) -> None:
        self.root = root
        self.state = state
        # Callbacks for the controller to connect later.
        self.on_start = on_start
        self.on_stop = on_stop

        self.monitoring_text = tk.StringVar(value="Inactive")
        self.camera_text = tk.StringVar(value="Checking...")
        self.people_text = tk.StringVar(value="--")
        self.message_text = tk.StringVar(value="Checking camera availability...")

        self._configure_window()
        self._build_layout()

    def _configure_window(self) -> None:
        self.root.title("Red-Handed")
        self.root.geometry("1040x860")
        self.root.minsize(940, 800)
        self.root.configure(background="#f3f4f6")

        style = ttk.Style(self.root)
        style.configure("Title.TLabel", font=("Segoe UI", 22, "bold"))
        style.configure("Heading.TLabel", font=("Segoe UI", 12, "bold"))
        style.configure("Status.TLabel", font=("Segoe UI", 13, "bold"))
        style.configure("Message.TLabel", foreground="#374151")

    def _build_layout(self) -> None:
        shell = ttk.Frame(self.root, padding=16)
        shell.pack(fill=tk.BOTH, expand=True)
        shell.columnconfigure(1, weight=1)
        shell.rowconfigure(0, weight=1)

        content = ttk.Frame(shell)
        content.grid(row=0, column=1, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(4, weight=1)

        ttk.Label(content, text="Red-Handed", style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            content,
            text="Camera monitoring and face-based person counting",
            foreground="#4b5563",
        ).grid(row=1, column=0, sticky="w", pady=(0, 14))

        status_row = ttk.Frame(content)
        status_row.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        for column in range(3):
            status_row.columnconfigure(column, weight=1)

        self._status_card(status_row, 0, "Monitoring Status", self.monitoring_text)
        self._status_card(status_row, 1, "Camera Status", self.camera_text)
        self._status_card(status_row, 2, "Detected People", self.people_text)

        controls = ttk.Frame(content)
        controls.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        for column in range(2):
            controls.columnconfigure(column, weight=1)

        self.start_button = ttk.Button(
            controls, text="Start Monitoring", command=self.start_monitoring
        )
        self.start_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.stop_button = ttk.Button(
            controls, text="Stop Monitoring", command=self.stop_monitoring
        )
        self.stop_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        preview_group = ttk.LabelFrame(content, text="Camera Preview", padding=12)
        preview_group.grid(row=4, column=0, sticky="nsew")
        preview_group.columnconfigure(0, weight=1)
        preview_group.rowconfigure(0, weight=1)

        self.preview = PreviewCanvas(preview_group)
        self.preview.grid(row=0, column=0, sticky="nsew")

        ttk.Label(
            content,
            textvariable=self.message_text,
            style="Message.TLabel",
            wraplength=720,
        ).grid(row=7, column=0, sticky="ew", pady=(8, 0))

        self._refresh_controls()

    @staticmethod
    def _status_card(
        parent: ttk.Frame, column: int, title: str, value: tk.StringVar
    ) -> None:
        card = ttk.LabelFrame(parent, text=title, padding=12)
        card.grid(
            row=0,
            column=column,
            sticky="ew",
            padx=(0 if column == 0 else 6, 0),
        )
        ttk.Label(card, textvariable=value, style="Status.TLabel").pack(anchor="w")

    def _refresh_status(self) -> None:
        state = self.state
        self.monitoring_text.set(state.monitoring_status.value)
        self.camera_text.set(state.camera_status.value)
        self._refresh_controls()

    def _refresh_controls(self) -> None:
        state = self.state
        active = state.monitoring_status is MonitoringStatus.ACTIVE
        available = state.camera_status is CameraStatus.AVAILABLE
        self.start_button.configure(
            state=tk.NORMAL if available and not active else tk.DISABLED
        )
        self.stop_button.configure(state=tk.NORMAL if active else tk.DISABLED)

    def start_monitoring(self) -> None:
        """FR1.1 - Ask the controller to start monitoring."""
        if self.on_start is not None:
            self.on_start()
        self._refresh_status()

    def stop_monitoring(self) -> None:
        """FR1.3 - Ask the controller to stop monitoring."""
        if self.on_stop is not None:
            self.on_stop()
        self.preview.clear("Camera preview is inactive")
        self._refresh_status()
