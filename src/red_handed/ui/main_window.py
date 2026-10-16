# TODO [FR1, FR12]: Present monitoring controls and system status.

"""Tkinter dashboard: status, monitoring controls and a camera preview."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import cv2
from PIL import Image, ImageTk

from red_handed.core.monitoring import MonitoringController
from red_handed.core.system_state import CameraStatus, MonitoringStatus


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

    def __init__(
        self,
        root: tk.Tk,
        controller: MonitoringController,
    ) -> None:
        self.root = root
        self.controller = controller
        self.state = controller.state

        # Keep one scheduled frame callback so repeated Start cannot create loops.
        self._frame_after_id: str | None = None
        self._closed = False

        self.monitoring_text = tk.StringVar(value="Inactive")
        self.camera_text = tk.StringVar(value="Checking...")
        self.people_text = tk.StringVar(value="--")
        self.message_text = tk.StringVar(
            value="Checking camera availability..."
        )

        self._configure_window()
        self._build_layout()

        # Closing the window must also release camera and detector resources.
        self.root.protocol("WM_DELETE_WINDOW", self.close)

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
                # Allows recovery after reconnecting a camera or fixing permissions.
        self.retry_button = ttk.Button(
            controls,
            text="Retry Camera",
            command=self.retry_camera,
        )
        self.retry_button.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(8, 0),
        )

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

    def initialize(self) -> None:
        """Check camera availability after Tk has created the dashboard."""
        self.retry_camera()

    def _refresh_status(self) -> None:
        """Display the controller's latest state and detection result."""
        self.monitoring_text.set(self.state.monitoring_status.value)
        self.camera_text.set(self.state.camera_status.value)

        result = self.controller.detection
        self.people_text.set(
            "--" if result is None else str(result.person_count)
        )

        if self.state.camera_error:
            self.message_text.set(self.state.camera_error)
        elif self.controller.detection_error:
            self.message_text.set(self.controller.detection_error)
        elif self.state.monitoring_status is MonitoringStatus.ACTIVE:
            self.message_text.set("Monitoring is active.")
        else:
            self.message_text.set("Ready. Select Start Monitoring.")

        self._refresh_controls()

    def _refresh_controls(self) -> None:
        """Enable only actions that make sense for the current state."""
        active = self.state.monitoring_status is MonitoringStatus.ACTIVE
        available = self.state.camera_status is CameraStatus.AVAILABLE

        self.start_button.configure(
            state=tk.NORMAL if available and not active else tk.DISABLED
        )
        self.stop_button.configure(
            state=tk.NORMAL if active else tk.DISABLED
        )
        self.retry_button.configure(
            state=tk.DISABLED if active else tk.NORMAL
        )

    def retry_camera(self) -> None:
        """Refresh availability without automatically starting monitoring."""
        if self._closed:
            return
        if self.state.monitoring_status is MonitoringStatus.ACTIVE:
            return

        available = self.controller.refresh_camera_availability()
        self.preview.clear(
            "Camera preview is inactive"
            if available
            else "Camera unavailable. Check the connection and select Retry Camera."
        )
        self._refresh_status()

    def start_monitoring(self) -> None:
        """Start capture and create one frame-update loop."""
        if self._closed:
            return

        self._cancel_frame_loop()
        started = self.controller.start_monitoring()
        self._refresh_status()

        if started:
            self._update_frame()
        else:
            self.preview.clear(
                self.state.camera_error or "Camera unavailable."
            )

    def stop_monitoring(self) -> None:
        """Cancel future updates, release the camera, and clear stale images."""
        if self._closed:
            return

        self._cancel_frame_loop()
        self.controller.stop_monitoring()
        self.preview.clear("Camera preview is inactive")
        self._refresh_status()

    def _update_frame(self) -> None:
        """Read, detect, and display one frame before scheduling another."""
        self._frame_after_id = None

        if self._closed:
            return
        if self.state.monitoring_status is not MonitoringStatus.ACTIVE:
            return

        frame = self.controller.read_frame()
        self._refresh_status()

        if frame is None:
            # Camera loss has already stopped monitoring in the controller.
            self.preview.clear(
                self.state.camera_error or "Camera preview is inactive"
            )
            return

        try:
            self._show_frame(frame)
        except Exception as error:
            # Do not leave the camera running behind a broken preview.
            self.stop_monitoring()
            self.message_text.set(f"Camera preview unavailable: {error}")
            return

        # Tk processes button clicks between callbacks.
        # 33 ms is a scheduling delay, not a guaranteed 30 FPS rate.
        self._frame_after_id = self.root.after(33, self._update_frame)

    def _show_frame(self, frame) -> None:
        """Convert OpenCV's BGR pixels into a Tk-compatible preview image."""
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(rgb)

        # Fit inside the preview without stretching the image.
        image.thumbnail(
            (
                max(1, self.preview.winfo_width()),
                max(1, self.preview.winfo_height()),
            ),
            Image.Resampling.LANCZOS,
        )

        photo = ImageTk.PhotoImage(image=image, master=self.root)

        # PreviewCanvas keeps a reference to prevent image garbage collection.
        self.preview.show_image(photo)

    def _cancel_frame_loop(self) -> None:
        """Remove the pending callback before stopping or restarting."""
        if self._frame_after_id is not None:
            self.root.after_cancel(self._frame_after_id)
            self._frame_after_id = None

    def close(self) -> None:
        """Cancel updates and release resources before destroying the window."""
        if self._closed:
            return

        self._closed = True
        self._cancel_frame_loop()

        try:
            self.controller.close()
        finally:
            self.root.destroy()
