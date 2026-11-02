# TODO [FR1, FR12]: Present monitoring controls and system status.

"""Tkinter dashboard: status, monitoring controls, preview and calibration."""

from __future__ import annotations

from dataclasses import replace
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk
import logging

from red_handed.core.monitoring import MonitoringController
from red_handed.core.settings import MonitoringSettings
from red_handed.core.system_state import CameraStatus, MonitoringStatus
from red_handed.ui.calibration_view import CalibrationView, detection_labels
from red_handed.ui.zone_preview import ZonePreview
from red_handed.ui.settings_view import SettingsView
from red_handed.storage.settings_store import SettingsStore
from red_handed.core.protection import ProtectionManager
from red_handed.core.settings import ProtectionSettings
from red_handed.system.hotkey_manager import HotkeyManager, WindowsHotkeyBackend
from red_handed.ui.protection_surface import TkProtectionSurface
from red_handed.ui.protection_view import ProtectionView
from red_handed.ui.application_view import ApplicationView
from red_handed.core.applications import ActiveApplication, ApplicationAwarePolicy
from red_handed.core.events import EventRecorder
from red_handed.storage.event_store import EventStore
from red_handed.system.active_application import ActiveApplicationDetector
from red_handed.ui.event_history_view import EventHistoryView
from red_handed.ui.static_web_opener import StaticWebOpener


class MainWindow:
    """Present status, monitoring controls, retry, and a live preview."""

    PREVIEW_SIZE = (640, 360)
    FRAME_INTERVAL_MS = 33

    def __init__(
        self,
        root: tk.Tk,
        controller: MonitoringController,
        settings_store: SettingsStore | None = None,
        *,
        enable_hotkeys: bool = True,
    ) -> None:
        self.root = root
        self.controller = controller
        self._closed = False
        self._enable_hotkeys = enable_hotkeys
        self._hotkey_job = None
        self._test_job = None
        self._hotkey_error = None
        self.hotkeys = None
        self._foreground_job = None
        self._foreground_detector = None
        self._last_external_application = ActiveApplication(
            error="Foreground application has not been checked."
        )
        self.recorder = None
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
        
        # load() already populated both monitoring and protection settings.
        self.protection_settings = self.settings_store.protection_settings
        self.application_settings = self.settings_store.application_settings

        # The surface creates its actual window only when protection is shown.
        self.web_opener = StaticWebOpener()
        self.surface = TkProtectionSurface(
            root,
            toggle_manual=self.toggle_manual,
            stop_monitoring=self.stop_monitoring,
            close_app=self.close,
            dismiss_test=self.end_test_protection,
        )
        self.protection = ProtectionManager(
            controller.state,
            self.surface,
            self.protection_settings.mode,
            web_opener=self.web_opener,
        )

        self.protection_text = tk.StringVar(master=root, value="Protection: Inactive")
        self.hotkey_text = tk.StringVar(master=root, value="Emergency hotkey: starting")

        self.monitoring_text = tk.StringVar(value="Inactive")
        self.camera_text = tk.StringVar(value="Checking...")
        self.people_text = tk.StringVar(value="--")
        self.detection_text = tk.StringVar(value="Detection inactive")
        self.risk_text = tk.StringVar(value="Privacy Risk: Inactive (monitoring stopped)")
        self.settings_notice = tk.StringVar(value=self.settings_store.last_error or "")
        self.message_text = tk.StringVar(value="Checking camera availability...")

        self._configure_window()
        self._build_layout()
        # Keep history beside the selected settings file. Tests using temporary
        # settings therefore also use temporary history rather than real user data.
        event_path = self.settings_store.path.with_name("events.json")
        self.recorder = EventRecorder(EventStore(event_path))

        self.controller.recorder = self.recorder
        self.protection.recorder = self.recorder

        self.history_view = EventHistoryView(self.content, self.recorder)
        self.history_view.grid(
            row=8, column=0, sticky="nsew", pady=(8, 0)
        )
        self.history_view.grid_remove()

        # An enabled gate starts blocked until a foreground app is known.
        self.protection.set_application_allowed(
            ApplicationAwarePolicy.allows(
                self.application_settings,
                self._last_external_application,
            )
        )
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._camera_check_job = self.root.after(100, self._initial_camera_check)
        self.controller.attach_protection(self.protection)

        if self._enable_hotkeys:
            try:
                self._ensure_hotkeys()
                self.hotkeys.configure(self.protection_settings.hotkey)
            except Exception as error:
                # Startup conflicts must not disable the onscreen emergency button.
                self._hotkey_error = str(error)

            self._hotkey_job = self.root.after(50, self._poll_hotkeys)

        self._refresh_protection()
        # Poll independently of hotkeys and camera monitoring.
        self._foreground_job = self.root.after(
            250, self._poll_foreground_application
        )

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
        ttk.Button(sidebar, text="Privacy Zone Setup", command=self.show_calibration).pack(
            fill=tk.X, pady=3
        )
        ttk.Button(sidebar, text="Detection & Timing", command=self.show_settings).pack(
            fill=tk.X, pady=3
        )
        ttk.Button(
            sidebar,
            text="Protection Mode",
            command=self.show_protection,
        ).pack(fill=tk.X, pady=3)
        ttk.Button(
            sidebar,
            text="Protected Applications",
            command=self.show_applications,
        ).pack(fill=tk.X, pady=3)
        ttk.Button(
            sidebar,
            text="Event History",
            command=self.show_history,
        ).pack(fill=tk.X, pady=3)
        content = ttk.Frame(shell)
        self.content = content
        content.grid(row=0, column=1, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(4, weight=1)

        ttk.Label(content, text="Red-Handed", style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            content,
            text="Protect your screen from shoulder surfers.\n"
                 "Automatically cover your screen when an additional person is detected in your saved privacy zone.",
            foreground="#4b5563",
            wraplength=650,
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
         # Manual protection remains available when monitoring or the camera is off.
        self.emergency_button = ttk.Button(
            controls,
            text="Emergency Protect / Toggle Manual",
            command=self.toggle_manual,
        )
        self.emergency_button.grid(
            row=1,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(8, 0),
        )

        preview_group = ttk.LabelFrame(content, text="Camera Preview", padding=12)
        preview_group.grid(row=4, column=0, sticky="nsew")
        preview_group.columnconfigure(0, weight=1)
        preview_group.rowconfigure(0, weight=1)

        self.preview = ZonePreview(
            preview_group,
            lambda: self.message_text.set(
                "Unsaved zone. Click Save Zone to use it; any saved zone stays in use until then."
            ),
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
            content, self.people_text, self.save_zone, self.discard_zone_draft
        )
        self.calibration.grid(row=8, column=0, sticky="ew", pady=(8, 0))
        self.calibration.grid_remove()
        ttk.Button(
            self.calibration,
            text="Test Protection (5 seconds)",
            command=self.begin_test_protection,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=4)
    
        self.settings_view = SettingsView(
            content, lambda: self.controller.settings, self.save_settings
        )
        self.settings_view.grid(row=8, column=0, sticky="ew", pady=(8, 0))
        self.settings_view.grid_remove()
        ttk.Label(content, textvariable=self.settings_notice, wraplength=650).grid(
            row=9, column=0, sticky="ew"
        )
        
        self.protection_view = ProtectionView(
            content,
            lambda: self.protection_settings,
            self.save_protection_settings,
        )
        self.protection_view.grid(
            row=8, column=0, sticky="ew", pady=(8, 0)
        )
        self.protection_view.grid_remove()

        self.application_view = ApplicationView(
            content,
            lambda: self.application_settings,
            self.save_application_settings,
        )
        self.application_view.grid(row=8, column=0, sticky="ew", pady=(8, 0))
        self.application_view.grid_remove()

        ttk.Label(
            content,
            textvariable=self.protection_text,
            wraplength=650,
        ).grid(row=10, column=0, sticky="ew", pady=(6, 0))

        ttk.Label(
            content,
            textvariable=self.hotkey_text,
            wraplength=650,
        ).grid(row=11, column=0, sticky="ew")

        self._refresh_controls()

    def show_home(self) -> None:
        """Show the dashboard without changing camera ownership or monitoring."""
        self.calibration.grid_remove()
        self.settings_view.grid_remove()
        if self.preview.draft_zone is not None:
            self.discard_zone_draft()
        self.preview.set_editing(False)
        self.protection_view.grid_remove()
        self.application_view.grid_remove()
        self.history_view.grid_remove()

    def show_calibration(self) -> None:
        """FR12.3 / FR12.4: share the running preview and current count."""
        self.calibration.grid()
        self.settings_view.grid_remove()
        self.preview.set_editing(True)
        self.protection_view.grid_remove()
        self.application_view.grid_remove()
        self.history_view.grid_remove()

    def show_protection(self) -> None:
        """Open protection settings and discard stale edits in that panel."""
        self.show_home()
        self.protection_view.reload()
        self.protection_view.grid()

    def show_applications(self) -> None:
        """Open protected-application settings and discard stale edits."""
        self.show_home()
        self.application_view.reload()
        self.application_view.grid()

    def save_application_settings(self, settings) -> None:
        """Persist first, then immediately apply the updated automatic gate."""
        self.settings_store.save(
            self.controller.settings,
            applications=settings,
        )
        self.application_settings = settings

        allowed = ApplicationAwarePolicy.allows(
            settings,
            self._last_external_application,
        )
        self.protection.set_application_allowed(allowed)
        self._refresh_protection()
    def show_history(self):
        """Open the history panel and take a fresh recorder snapshot."""
        self.show_home()
        self.history_view.refresh(force=True)
        self.history_view.grid()

    def _poll_foreground_application(self):
        """Reevaluate automatic protection without modifying risk timing."""
        self._foreground_job = None
        if self._closed:
            return

        try:
            if self._foreground_detector is None:
                self._foreground_detector = ActiveApplicationDetector()

            protection_window = None
            window = self.surface.window
            if window is not None and self.controller.state.protection_active:
                protection_window = window.winfo_id()

            active = self._foreground_detector.detect(protection_window)
            is_decoy_website = (
                active.process_id is not None
                and active.process_id == self.web_opener.browser_pid
            )
            # Chrome can take focus before its constructor returns its PID.
            # Retain the preceding app during that brief startup interval.
            decoy_starting = self.web_opener.starting
            if not active.protection_surface and not is_decoy_website and not decoy_starting:
                self._last_external_application = active
            elif active.protection_surface and not (
                window is not None and self.controller.state.protection_active
            ):
                # Our ordinary dashboard is not a protected external application.
                self._last_external_application = ActiveApplication(
                    error="Red-Handed has focus."
                )

            # When our visible protection surface takes focus, retain the last
            # external app. Otherwise the overlay could disable its own gate.
            allowed = ApplicationAwarePolicy.allows(
                self.application_settings,
                self._last_external_application,
            )
        except Exception:
            self._last_external_application = ActiveApplication(
                error="Foreground application unavailable."
            )
            allowed = ApplicationAwarePolicy.allows(
                self.application_settings,
                self._last_external_application,
            )

        self.protection.set_application_allowed(allowed)
        self._refresh_protection()
        self.history_view.refresh()

        if not self._closed:
            self._foreground_job = self.root.after(
                250, self._poll_foreground_application
            )

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

    def discard_zone_draft(self) -> None:
        self.preview.discard_draft()
        if self.preview.saved_zone is not None:
            self.message_text.set("Unsaved drawing discarded. Your saved zone stays in use for monitoring.")
        else:
            self.message_text.set("Unsaved drawing discarded. Open Privacy Zone Setup to draw and save a zone.")

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
        self._refresh_protection()

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

    def _ensure_hotkeys(self) -> None:
        """Create the Windows service lazily, allowing retry after startup failure."""
        if self.hotkeys is not None:
            return

        if not self._enable_hotkeys:
            raise OSError("Global hotkeys are disabled for this test instance.")

        backend = WindowsHotkeyBackend()
        self.hotkeys = HotkeyManager(backend, self.toggle_manual)

    def _poll_hotkeys(self) -> None:
        """Dispatch queued hotkey events on Tk's thread, never the worker thread."""
        self._hotkey_job = None
        if self._closed:
            return

        try:
            if self.hotkeys is not None:
                self.hotkeys.poll()
        except Exception as error:
            self._hotkey_error = str(error)

        self._refresh_protection()
        if not self._closed:
            self._hotkey_job = self.root.after(50, self._poll_hotkeys)

    def _refresh_protection(self) -> None:
        """Show actual protection state and hotkey availability."""
        if self._closed:
            return

        state = self.controller.state
        if state.protection_error:
            self.protection_text.set(
                f"Protection error: {state.protection_error}"
            )
        elif state.protection_active:
            self.protection_text.set(
                f"Protection: {self.protection.active_mode.value} "
                f"({self.protection.source})"
                + (f" — {self.protection.notice}" if self.protection.notice else "")
            )
        else:
            self.protection_text.set("Protection: Inactive")

        if not self._enable_hotkeys:
            self.hotkey_text.set("Global hotkeys disabled for testing.")
        elif self._hotkey_error:
            self.hotkey_text.set(
                f"Hotkey problem: {self._hotkey_error} "
                "The Emergency Protect button remains available."
            )
        elif self.hotkeys is not None and self.hotkeys.current is not None:
            self.hotkey_text.set(
                f"Emergency hotkey: {self.hotkeys.current.text}"
            )
        else:
            self.hotkey_text.set(
                "No global hotkey registered. Use Emergency Protect."
            )

    def toggle_manual(self) -> None:
        """Toggle manual protection independently of camera and risk state."""
        if self._closed:
            return

        if self.controller.state.test_protection_requested:
            # During a test, the shortcut acts as an early dismissal.
            self.end_test_protection()
            return

        self.protection.toggle_manual()
        self._refresh_protection()

    def begin_test_protection(self) -> None:
        """Show a labelled test that expires without clearing real requests."""
        if self._closed:
            return

        try:
            self.protection.begin_test()
        except ValueError as error:
            self.settings_notice.set(str(error))
            return

        if self._test_job is not None:
            self.root.after_cancel(self._test_job)

        self._test_job = self.root.after(5000, self.end_test_protection)
        self._refresh_protection()

    def end_test_protection(self) -> None:
        """End only the test request; automatic/manual requests are independent."""
        if self._closed:
            return

        if self._test_job is not None:
            self.root.after_cancel(self._test_job)
            self._test_job = None

        self.protection.end_test()
        self._refresh_protection()

    def save_protection_settings(self, settings: ProtectionSettings) -> None:
        """Reserve the new shortcut, persist settings, then replace the old one."""
        if not isinstance(settings, ProtectionSettings):
            raise ValueError("Invalid protection settings.")

        try:
            self._ensure_hotkeys()
            # A conflicting candidate must fail before anything is written.
            self.hotkeys.prepare(settings.hotkey)
        except Exception as error:
            raise ValueError(str(error)) from error

        try:
            # Keep the current zone, sensitivity, and delays unchanged.
            self.settings_store.save(
                self.controller.settings,
                protection=settings,
            )
        except Exception as error:
            try:
                # Release the candidate; retain the old working shortcut.
                self.hotkeys.rollback()
            except Exception as rollback_error:
                self._hotkey_error = (
                    f"Could not release the unsaved shortcut: {rollback_error}"
                )
                self._refresh_protection()

            raise OSError(f"Protection settings were not saved: {error}") from error

        self.protection_settings = settings

        try:
            self.hotkeys.commit()
        except Exception as error:
            # commit() selects the new binding before unregistering the old one.
            # The settings were saved; report a cleanup issue accurately.
            self._hotkey_error = (
                f"Settings saved, but old shortcut cleanup failed: {error}"
            )
        else:
            self._hotkey_error = None

        self.protection.select_mode(settings.mode)
        self._refresh_protection()

    def close(self) -> None:
        """Remove callbacks and attempt every resource cleanup exactly once."""
        if self._closed:
            return
        self._closed = True

        logger = logging.getLogger(__name__)

        for attribute in (
            "_camera_check_job",
            "_frame_job",
            "_hotkey_job",
            "_test_job",
            "_foreground_job",
        ):
            job = getattr(self, attribute, None)
            setattr(self, attribute, None)
            if job is not None:
                try:
                    self.root.after_cancel(job)
                except tk.TclError:
                    logger.exception("Could not cancel %s", attribute)

        cleanup_steps = []
        if self.hotkeys is not None:
            cleanup_steps.append(self.hotkeys.close)

        cleanup_steps.extend([
            lambda: self.controller.attach_protection(None),
            self.protection.close,
            self.root.destroy,
            self.controller.close,
        ])

        # Existing headless test fixtures may not construct a recorder.
        # Close it last so any already-submitted writes finish before exit.
        recorder = getattr(self, "recorder", None)
        if recorder is not None:
            cleanup_steps.append(recorder.close)
        # Remove the surface and release the shortcut before waiting for the
        # detector worker. One failed cleanup must not skip the remaining steps.
        for cleanup in cleanup_steps:
            try:
                cleanup()
            except Exception:
                logger.exception("Application cleanup failed")
