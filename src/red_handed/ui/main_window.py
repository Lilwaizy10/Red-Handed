# TODO [FR1, FR12]: Present monitoring controls and system status.

"""Tkinter dashboard: status, monitoring controls, preview and calibration."""

from __future__ import annotations

from dataclasses import replace
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk

from red_handed.core.monitoring import MonitoringController
from red_handed.core.settings import MonitoringSettings
from red_handed.core.system_state import CameraStatus, MonitoringStatus
from red_handed.ui.calibration_view import CalibrationView, detection_labels
from red_handed.ui.zone_preview import ZonePreview
from red_handed.ui.settings_view import SettingsView
from red_handed.storage.settings_store import SettingsStore


class MainWindow:
    """Present status, monitoring controls, retry, and a live preview."""

    PREVIEW_SIZE = (640, 360)
    FRAME_INTERVAL_MS = 33

    def __init__(self, root: tk.Tk, controller: MonitoringController,
                 settings_store: SettingsStore | None = None) -> None:
        self.root = root
        self.controller = controller
        # Tests can inject a temporary store instead of using real user settings.
        self.settings_store = settings_store if settings_store is not None else SettingsStore()
        self._frame_job: str | None = None
        self._camera_check_job: str | None = None
        self._preview_photo: ImageTk.PhotoImage | None = None

        # Load once at startup so saved zone/sensitivity/delays reach the controller.
        # The store supplies defaults and sets last_error if the file is unreadable
        # or invalid. This must run BEFORE settings_notice and preview.saved_zone
        # read their values below. (Harmless if the entry point also applies it.)
        self.controller.apply_settings(self.settings_store.load())

        self.monitoring_text = tk.StringVar(value="Inactive")
        self.camera_text = tk.StringVar(value="Checking...")
        self.people_text = tk.StringVar(value="--")
        self.detection_text = tk.StringVar(value="Detection inactive")
        self.risk_text = tk.StringVar(value="Privacy Risk: Inactive (monitoring stopped)")
        self.settings_notice = tk.StringVar(value=self.settings_store.last_error or "")
        self.message_text = tk.StringVar(value="Checking camera availability...")

        self._configure_window()
        self._build_layout()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._camera_check_job = self.root.after(100, self._initial_camera_check)

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

        sidebar = ttk.Frame(shell, padding=(8, 12), width=180)
        sidebar.grid(row=0, column=0, sticky="nsw", padx=(0, 16))
        sidebar.grid_propagate(False)

        ttk.Label(sidebar, text="RED-HANDED", style="Heading.TLabel").pack(
            anchor="w", pady=(0, 20)
        )
        ttk.Button(sidebar, text="Home", command=self.show_home).pack(fill=tk.X, pady=3)
        ttk.Button(sidebar, text="Status / Calibration", command=self.show_calibration).pack(
            fill=tk.X, pady=3
        )
        ttk.Button(sidebar, text="Detection & Timing", command=self.show_settings).pack(
            fill=tk.X, pady=3
        )

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
        for column in range(3):
            controls.columnconfigure(column, weight=1)

        self.start_button = ttk.Button(
            controls, text="Start Monitoring", command=self.start_monitoring
        )
        self.start_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.stop_button = ttk.Button(
            controls, text="Stop Monitoring", command=self.stop_monitoring
        )
        self.stop_button.grid(row=0, column=1, sticky="ew", padx=6)
        self.retry_button = ttk.Button(
            controls, text="Retry Camera Access", command=self.retry_camera
        )
        self.retry_button.grid(row=0, column=2, sticky="ew", padx=(6, 0))

        preview_group = ttk.LabelFrame(content, text="Camera Preview", padding=12)
        preview_group.grid(row=4, column=0, sticky="nsew")
        preview_group.columnconfigure(0, weight=1)
        preview_group.rowconfigure(0, weight=1)

        self.preview = ZonePreview(
            preview_group,
            lambda: self.message_text.set("Unsaved zone. Select Save Zone to apply."),
        )
        self.preview.saved_zone = self.controller.settings.privacy_zone
        self.preview.grid(row=0, column=0, sticky="nsew")

        ttk.Label(
            content, textvariable=self.detection_text, wraplength=570,
        ).grid(row=5, column=0, sticky="ew", pady=(8, 0))

        ttk.Label(content, textvariable=self.risk_text, wraplength=650).grid(
            row=6, column=0, sticky="ew", pady=6
        )
        ttk.Label(
            content,
            textvariable=self.message_text,
            style="Message.TLabel",
            wraplength=720,
        ).grid(row=7, column=0, sticky="ew", pady=(8, 0))

        # Calibration and settings panels share row 8; only one is visible at a time.
        self.calibration = CalibrationView(
            content, self.people_text, self.save_zone, self.preview.discard_draft
        )
        self.calibration.grid(row=8, column=0, sticky="ew", pady=(8, 0))
        self.calibration.grid_remove()
        # The getter is a lambda so the view always reads the controller's latest
        # (frozen, replaced-on-save) settings object.
        self.settings_view = SettingsView(
            content, lambda: self.controller.settings, self.save_settings
        )
        self.settings_view.grid(row=8, column=0, sticky="ew", pady=(8, 0))
        self.settings_view.grid_remove()
        ttk.Label(content, textvariable=self.settings_notice, wraplength=650).grid(
            row=9, column=0, sticky="ew"
        )

        self._refresh_controls()

    def show_home(self) -> None:
        """Show the dashboard without changing camera ownership or monitoring."""
        self.calibration.grid_remove()
        self.settings_view.grid_remove()
        self.preview.set_editing(False)

    def show_calibration(self) -> None:
        """FR12.3 / FR12.4: share the running preview and current count."""
        self.calibration.grid()
        self.settings_view.grid_remove()
        self.preview.set_editing(True)

    def show_settings(self) -> None:
        self.show_home()
        # Discard stale typed text from an earlier visit to this panel.
        self.settings_view.reload()
        self.settings_view.grid()

    def save_settings(self, settings: MonitoringSettings) -> None:
        """Persist before changing active settings; failed saves preserve previous values.

        Called by SettingsView and by save_zone. Raises ValueError/OSError on
        failure so the caller can show the message. This deliberately does NOT
        touch the zone preview: saving timing settings must not discard an
        unsaved zone drawing.
        """
        try:
            self.settings_store.save(settings)
        except TypeError as error:
            # The callers only handle ValueError and OSError, so convert here;
            # otherwise Tk would print a traceback and the user would see nothing.
            raise ValueError(str(error)) from error
        # Only a successful save is allowed to change the active settings.
        self.controller.apply_settings(settings)
        self.settings_notice.set("")
        self._refresh_detection()

    def save_zone(self) -> None:
        zone = self.preview.draft_zone
        if zone is None:
            self.message_text.set("Draw a non-empty rectangle on the live calibration preview first.")
            return
        try:
            # replace() changes only the zone, preserving sensitivity and both delays.
            self.save_settings(replace(self.controller.settings, privacy_zone=zone))
        except (ValueError, OSError) as error:
            # Keep the previous active zone and the unsaved draft so the user can retry.
            self.message_text.set(f"Zone not saved: {error}")
            return
        # Zone-specific updates belong here, after a successful save only.
        self.preview.saved_zone = zone
        self.preview.discard_draft()
        self.message_text.set("Privacy zone saved. Risk timing restarts with the next detection.")

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

    def _initial_camera_check(self) -> None:
        self._camera_check_job = None
        self.retry_camera()

    # FR12.1 / FR12.2 - Status is always represented with text, not colour alone.
    def _refresh_status(self) -> None:
        state = self.controller.state
        self.monitoring_text.set(state.monitoring_status.value)
        self.camera_text.set(state.camera_status.value)
        self._refresh_detection()
        self._refresh_controls()

    def _refresh_detection(self) -> None:
        count, status = detection_labels(self.controller.state)
        self.people_text.set(count)
        self.detection_text.set(status)
        state = self.controller.state
        zone = "Configured" if state.privacy_zone is not None else "Unconfigured"
        inside = "--" if state.additional_person_in_zone is None else ("Yes" if state.additional_person_in_zone else "No")
        if state.monitoring_status is MonitoringStatus.INACTIVE:
            risk = "Inactive (monitoring stopped)"
        elif state.privacy_zone is None:
            risk = "Unavailable (configure a privacy zone)"
        elif state.risk_status is None:
            risk = "Unavailable (waiting for valid detection)"
        else:
            risk = state.risk_status.value
        self.risk_text.set(f"Privacy Zone: {zone} | Additional Person in Privacy Zone: {inside}\nPrivacy Risk: {risk}")

    def _refresh_controls(self) -> None:
        state = self.controller.state
        active = state.monitoring_status is MonitoringStatus.ACTIVE
        available = state.camera_status is CameraStatus.AVAILABLE
        self.start_button.configure(
            state=tk.NORMAL if available and not active else tk.DISABLED
        )
        self.stop_button.configure(state=tk.NORMAL if active else tk.DISABLED)
        self.retry_button.configure(
            state=tk.NORMAL if not active and not available else tk.DISABLED
        )

    def retry_camera(self) -> None:
        """FR13.4 - Let the user retry after a camera error."""
        if self._camera_check_job is not None:
            self.root.after_cancel(self._camera_check_job)
            self._camera_check_job = None
        self.camera_text.set("Checking...")
        self.message_text.set("Checking camera availability...")
        self.root.update_idletasks()

        if self.controller.refresh_camera_availability():
            self.message_text.set("Camera is ready. Select Start Monitoring to begin.")
            self.preview.clear("Camera preview is inactive")
        else:
            self.message_text.set(
                self.controller.state.camera_error
                or "Camera unavailable. Check the connection or permissions, then retry."
            )
            self.preview.clear("Camera unavailable")

        self._preview_photo = None
        self._refresh_status()

    def start_monitoring(self) -> None:
        """FR1.1 / FR1.2 - Start frame retrieval after camera verification."""
        if not self.controller.start_monitoring():
            self.message_text.set(
                self.controller.state.camera_error
                or "Privacy monitoring is unavailable because the camera cannot be accessed."
            )
            self.preview.clear("Camera unavailable")
            self._refresh_status()
            return

        self.message_text.set(
            "Monitoring is active. Camera frames are not stored or transmitted."
        )
        self._refresh_status()
        self._schedule_next_frame()

    def _schedule_next_frame(self) -> None:
        if self.controller.state.monitoring_status is MonitoringStatus.ACTIVE:
            self._frame_job = self.root.after(
                self.FRAME_INTERVAL_MS, self._update_preview
            )

    def _update_preview(self) -> None:
        self._frame_job = None
        frame = self.controller.read_frame()
        self._refresh_detection()
        if frame is None:
            self._preview_photo = None
            self.preview.clear("Camera unavailable")
            self.message_text.set(
                self.controller.state.camera_error
                or "Camera access was lost. Monitoring has stopped; retry camera access."
            )
            self._refresh_status()
            return

        try:
            image = Image.fromarray(frame[:, :, ::-1])
            size = (max(1, min(self.PREVIEW_SIZE[0], self.preview.winfo_width() - 4)),
                    max(1, min(self.PREVIEW_SIZE[1], self.preview.winfo_height() - 4)))
            image.thumbnail(size, Image.Resampling.LANCZOS)
            self._preview_photo = ImageTk.PhotoImage(image=image)
            self.preview.show_image(self._preview_photo)
        except Exception as exc:
            self.message_text.set(f"The camera frame could not be displayed: {exc}")

        self._schedule_next_frame()

    def stop_monitoring(self) -> None:
        """FR1.3 / FR1.4 - Stop frame retrieval and clear the preview."""
        if self._frame_job is not None:
            self.root.after_cancel(self._frame_job)
            self._frame_job = None
        self.controller.stop_monitoring()
        self._preview_photo = None
        self.preview.clear("Camera preview is inactive")
        self.message_text.set("Monitoring is inactive. Camera access has been released.")
        self._refresh_status()

    def close(self) -> None:
        """Release camera access before closing the window."""
        if self._camera_check_job is not None:
            self.root.after_cancel(self._camera_check_job)
            self._camera_check_job = None
        if self._frame_job is not None:
            self.root.after_cancel(self._frame_job)
            self._frame_job = None
        self.controller.close()
        self.root.destroy()
