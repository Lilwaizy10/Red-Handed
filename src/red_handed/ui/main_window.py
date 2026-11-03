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
from red_handed.ui.tutorial_controller import TutorialController, TutorialStep
from red_handed.ui.tutorial_view import ControlHighlighter, TutorialView
from red_handed.ui.customisation_controller import CustomisationContext, CustomisationController


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
        self._test_notice = None
        self._hotkey_error = None
        self.hotkeys = None
        self._foreground_job = None
        self._foreground_detector = None
        self._last_external_application = ActiveApplication(
            error="Foreground application has not been checked."
        )
        self.recorder = None
        self._current_view = "home"
        # Tests can inject a temporary store instead of using real user settings.
        self.settings_store = settings_store if settings_store is not None else SettingsStore()
        self._frame_job: str | None = None
        self._camera_check_job: str | None = None
        self._preview_photo: ImageTk.PhotoImage | None = None
        self._preview_error = False

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
        self.tutorial_highlighter = ControlHighlighter(root)
        self.tutorial = TutorialController(self._show_tutorial_step, self._hide_tutorial)
        self.customisation = CustomisationController(self._show_tutorial_step, self._hide_tutorial)
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
        self.home_button = ttk.Button(sidebar, text="Home", command=self.show_home)
        self.home_button.pack(fill=tk.X, pady=3)
        self.zone_setup_button = ttk.Button(
            sidebar, text="Privacy Zone Setup", command=self.show_calibration
        )
        self.zone_setup_button.pack(fill=tk.X, pady=3)
        self.timing_button = ttk.Button(sidebar, text="Detection & Timing", command=self.show_settings)
        self.timing_button.pack(fill=tk.X, pady=3)
        self.protection_mode_button = ttk.Button(
            sidebar,
            text="Protection Mode",
            command=self.show_protection,
        )
        self.protection_mode_button.pack(fill=tk.X, pady=3)
        self.applications_button = ttk.Button(
            sidebar,
            text="Protected Applications",
            command=self.show_applications,
        )
        self.applications_button.pack(fill=tk.X, pady=3)
        ttk.Button(
            sidebar,
            text="Event History",
            command=self.show_history,
        ).pack(fill=tk.X, pady=3)
        self.replay_tutorial_button = ttk.Button(
            sidebar, text="Replay tutorial", command=self.start_tutorial
        )
        self.replay_tutorial_button.pack(fill=tk.X, pady=(20, 3))
        self.customise_button = ttk.Menubutton(sidebar, text="Customise more")
        self.customise_menu = tk.Menu(self.customise_button, tearoff=False)
        for label, mode in (("Timing", "timing"), ("Emergency shortcut", "shortcut"),
                            ("Selected applications", "applications")):
            self.customise_menu.add_command(label=label, command=lambda mode=mode: self.start_customisation(mode))
        self.customise_button.configure(menu=self.customise_menu)
        self.customise_button.pack(fill=tk.X, pady=3)
        content = ttk.Frame(shell)
        self.content = content
        content.grid(row=0, column=1, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(4, weight=1)

        self.title_label = ttk.Label(content, text="Red-Handed", style="Title.TLabel")
        self.title_label.grid(row=0, column=0, sticky="w")
        self.intro_frame = ttk.Frame(content)
        self.intro_frame.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        self.intro_frame.columnconfigure(0, weight=1)
        self.intro_label = ttk.Label(
            self.intro_frame,
            text="Protect your screen from shoulder surfers.\n"
                 "Automatically cover your screen when an additional person is detected in your saved privacy zone.",
            foreground="#4b5563",
            wraplength=650,
        )
        self.intro_label.grid(row=0, column=0, columnspan=2, sticky="w")
        self.guide_button = ttk.Button(
            self.intro_frame, text="Guide me through setup", command=self.start_tutorial
        )
        self.guide_button.grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.home_test_button = ttk.Button(
            self.intro_frame, text="Test Protection (5 seconds)", command=self.begin_test_protection
        )
        self.home_test_button.grid(row=1, column=1, sticky="e", pady=(4, 0))
        self.tutorial_view = TutorialView(
            self.intro_frame,
            back=lambda: self._active_guide().back(),
            next_step=lambda: self._active_guide().next(),
            skip=lambda: self._active_guide().skip(),
            redraw=self._tutorial_alternate,
        )
        self.tutorial_view.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.tutorial_view.grid_remove()

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
            self._zone_draft_changed,
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
        self.calibration_test_button = ttk.Button(
            self.calibration,
            text="Test Protection (5 seconds)",
            command=self.begin_test_protection,
        )
        self.calibration_test_button.grid(row=3, column=0, columnspan=2, sticky="w", pady=4)
    
        self.settings_view = SettingsView(
            content, lambda: self.controller.settings, self.save_settings,
            on_change=self._sync_tutorial, on_saved=self._timing_settings_saved,
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
            on_change=self._sync_tutorial,
            on_saved=self._protection_settings_saved,
        )
        self.protection_view.grid(
            row=8, column=0, sticky="ew", pady=(8, 0)
        )
        self.protection_view.grid_remove()

        self.application_view = ApplicationView(
            content,
            lambda: self.application_settings,
            self.save_application_settings,
            on_change=self._sync_tutorial, on_saved=self._application_settings_saved,
            on_added=self._application_added,
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

    def start_tutorial(self) -> None:
        if not self._closed:
            self.customisation.skip()
            self.tutorial.start(self._tutorial_context())

    def _active_guide(self):
        return self.customisation if self.customisation.active else self.tutorial

    def start_customisation(self, mode) -> None:
        if not self._closed:
            self.tutorial.skip()
            self.customisation.skip()
            self.customisation.start(mode, self._tutorial_context())

    def _tutorial_alternate(self):
        if self.tutorial.active and self.tutorial.index == 6:
            button = self.tutorial_view.redraw_button
            self.customise_menu.post(button.winfo_rootx(), button.winfo_rooty() + button.winfo_height())
        else:
            self.tutorial.redraw()

    def _tutorial_context(self) -> CustomisationContext:
        state = self.controller.state
        runtime = (
            f"Monitoring: {state.monitoring_status.value.lower()}; camera: {state.camera_status.value.lower()}. "
            f"{self.protection_text.get()}."
        )
        if state.monitoring_status is MonitoringStatus.ACTIVE and not state.protection_active:
            if not ApplicationAwarePolicy.allows(self.application_settings, self._last_external_application):
                runtime += " Selected-app restriction currently blocks automatic protection."
            elif state.risk_status is None:
                runtime += " Waiting for valid detection."
        return CustomisationContext(
            camera_available=state.camera_status is CameraStatus.AVAILABLE,
            monitoring=state.monitoring_status is MonitoringStatus.ACTIVE,
            preview_ready=self.preview.has_image,
            zone_open=self._current_view == "calibration",
            saved_zone=self.controller.settings.privacy_zone is not None,
            draft_ready=self.preview.draft_ready,
            preview_error=self._preview_error,
            protection_open=self._current_view == "protection",
            protection_dirty=self.protection_view.has_unsaved_changes,
            protection_save_failed=self.protection_view.save_error is not None,
            home_open=self._current_view == "home",
            selected_mode=self.protection_settings.mode.value,
            hotkey=self.protection_settings.hotkey,
            hotkey_available=bool(self._enable_hotkeys and not self._hotkey_error and self.hotkeys is not None
                                 and self.hotkeys.current is not None),
            test_requested=state.test_protection_requested,
            automatic_requested=state.automatic_protection_requested,
            manual_requested=state.manual_protection_requested,
            protection_active=state.protection_active,
            actual_mode=self.protection.active_mode.value if self.protection.active_mode is not None else "",
            protection_error=state.protection_error or "",
            runtime_summary=runtime,
            timing_open=self._current_view == "settings",
            timing_dirty=self.settings_view.has_unsaved_changes,
            timing_error=self.settings_view.save_error or "",
            activation_delay=self.controller.settings.activation_delay,
            recovery_delay=self.controller.settings.recovery_delay,
            applications_open=self._current_view == "applications",
            applications_dirty=self.application_view.has_unsaved_changes,
            applications_error=self.application_view.save_error or "",
            applications_enabled=self.application_view.enabled.get(),
            applications_count=len(self.application_view.applications),
            saved_applications_enabled=self.application_settings.application_aware_enabled,
            saved_applications_count=len(self.application_settings.protected_applications),
        )

    def _protection_settings_saved(self) -> None:
        self.tutorial.protection_saved(self._tutorial_context())
        self.customisation.saved("shortcut", self._tutorial_context())

    def _timing_settings_saved(self):
        self.customisation.saved("timing", self._tutorial_context())

    def _application_settings_saved(self):
        self.customisation.saved("applications", self._tutorial_context())

    def _application_added(self):
        self.customisation.application_added(self._tutorial_context())

    def _sync_tutorial(self) -> None:
        for name in ("tutorial", "customisation"):
            guide = getattr(self, name, None)
            if guide is not None and guide.active:
                guide.update(self._tutorial_context())

    def _zone_draft_changed(self) -> None:
        if self.preview.draft_zone is not None:
            self.message_text.set(
                "Unsaved zone. Click Save Zone to use it; any saved zone stays in use until then."
            )
        else:
            self.message_text.set("No zone drawn. Click and drag inside the camera image.")
        self._sync_tutorial()

    def _show_tutorial_step(self, step: TutorialStep, index: int, total: int) -> None:
        self.title_label.grid_remove()
        self.intro_label.grid_remove()
        self.guide_button.grid_remove()
        self.tutorial_view.render(step, index, total)
        self.tutorial_view.grid()
        targets = {
            "start_monitoring": self.start_button,
            "retry_camera": self.retry_button,
            "stop_monitoring": self.stop_button,
            "privacy_zone": self.zone_setup_button,
            "preview": self.preview,
            "save_zone": self.calibration.save_button,
            "protection_mode": self.protection_mode_button,
            "protection_choices": self.protection_view,
            "save_protection": self.protection_view.save_button,
            "home": self.home_button,
            "test_protection": self.home_test_button,
            "timing": self.timing_button,
            "activation": self.settings_view.activation_entry,
            "recovery": self.settings_view.recovery_entry,
            "save_timing": self.settings_view.save_button,
            "hotkey": self.protection_view.hotkey_entry,
            "applications": self.applications_button,
            "enable_applications": self.application_view.enable_button,
            "add_application": self.application_view.add_button,
            "save_applications": self.application_view.save_button,
        }
        if step.target is None:
            self.tutorial_highlighter.clear()
        else:
            self.tutorial_highlighter.show(targets[step.target])

    def _hide_tutorial(self) -> None:
        self.tutorial_highlighter.clear()
        self.tutorial_view.grid_remove()
        self.title_label.grid()
        self.intro_label.grid()
        self._set_current_view(self._current_view)

    def _set_current_view(self, name: str) -> None:
        self._current_view = name
        if name == "home" and not self._active_guide().active:
            self.guide_button.grid()
        else:
            self.guide_button.grid_remove()
        if name == "home":
            self.home_test_button.grid()
        else:
            self.home_test_button.grid_remove()
        self._sync_tutorial()

    def _can_leave_view(self) -> bool:
        if self._active_guide().active:
            if self.preview.draft_zone is not None:
                self.message_text.set("Save Zone or Discard Draft before leaving Privacy Zone Setup. "
                                      "Your unsaved drawing has been kept.")
                return False
            for name, panel, label in (("settings", self.settings_view, "Save Settings"),
                                       ("applications", self.application_view, "Save Application Settings")):
                if self._current_view == name and panel.has_unsaved_changes:
                    self.message_text.set(f"{label} or Discard changes before leaving this panel. Your unsaved changes have been kept.")
                    return False
            if self._current_view == "protection" and self.protection_view.has_unsaved_changes:
                self.message_text.set("Save Protection Settings or Discard changes before leaving Protection Mode. "
                                      "Your unsaved changes have been kept.")
                return False
        return True

    def show_home(self) -> bool:
        """Show the dashboard without changing camera ownership or monitoring."""
        if not self._can_leave_view():
            return False
        self.calibration.grid_remove()
        self.settings_view.grid_remove()
        if self.preview.draft_zone is not None:
            self.discard_zone_draft()
        self.preview.set_editing(False)
        self.protection_view.grid_remove()
        self.application_view.grid_remove()
        self.history_view.grid_remove()
        self._set_current_view("home")
        return True

    def show_calibration(self) -> None:
        """FR12.3 / FR12.4: share the running preview and current count."""
        if self._current_view != "calibration" and not self._can_leave_view():
            return
        self.calibration.grid()
        self.settings_view.grid_remove()
        if not self.preview.editing:
            self.preview.set_editing(True)
        self.protection_view.grid_remove()
        self.application_view.grid_remove()
        self.history_view.grid_remove()
        self._set_current_view("calibration")

    def show_protection(self) -> None:
        """Open protection settings and discard stale edits in that panel."""
        if self._current_view == "protection":
            return
        if not self.show_home():
            return
        self.protection_view.reload()
        self.protection_view.grid()
        self._set_current_view("protection")

    def show_applications(self) -> None:
        """Open protected-application settings and discard stale edits."""
        if self._current_view == "applications":
            return
        if not self.show_home():
            return
        self.application_view.reload()
        self.application_view.grid()
        self._set_current_view("applications")

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
        if not self.show_home():
            return
        self.history_view.refresh(force=True)
        self.history_view.grid()
        self._set_current_view("history")

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
        if self._current_view == "settings":
            return
        if not self.show_home():
            return
        # Discard stale typed text from an earlier visit to this panel.
        self.settings_view.reload()
        self.settings_view.grid()
        self._set_current_view("settings")

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
        self._sync_tutorial()

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
            if getattr(self, "tutorial", None) is not None:
                self.tutorial.save_failed()
            return
        # Zone-specific updates belong here, after a successful save only.
        self.preview.saved_zone = zone
        self.preview.discard_draft()
        self.message_text.set("Privacy zone saved. Risk timing restarts with the next detection.")
        if getattr(self, "tutorial", None) is not None:
            self.tutorial.zone_saved(self._tutorial_context())

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
        self._sync_tutorial()

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
        self._update_test_controls()

    def _update_test_controls(self) -> None:
        state = self.controller.state
        blocked = state.test_protection_requested or state.automatic_protection_requested or state.manual_protection_requested
        for name in ("home_test_button", "calibration_test_button"):
            button = getattr(self, name, None)
            if button is not None:
                button.configure(state=tk.DISABLED if blocked else tk.NORMAL)

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
        self._preview_error = False
        self._refresh_status()

    def start_monitoring(self) -> None:
        """FR1.1 / FR1.2 - Start frame retrieval after camera verification."""
        self._preview_error = False
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
            self._preview_error = False
        except Exception as exc:
            self._preview_photo = None
            self._preview_error = True
            self.preview.clear("Camera preview unavailable")
            self.message_text.set(f"The camera frame could not be displayed: {exc}")

        self._sync_tutorial()
        self._schedule_next_frame()

    def stop_monitoring(self) -> None:
        """FR1.3 / FR1.4 - Stop frame retrieval and clear the preview."""
        if self._frame_job is not None:
            self.root.after_cancel(self._frame_job)
            self._frame_job = None
        self.controller.stop_monitoring()
        self._preview_photo = None
        self._preview_error = False
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
        self.hotkeys = HotkeyManager(backend, self._handle_hotkey)

    def _handle_hotkey(self):
        customisation = getattr(self, "customisation", None)
        if customisation is not None:
            customisation.shortcut_used()
        self.toggle_manual()

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
        self._update_test_controls()
        self._sync_tutorial()

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
            self._test_notice = str(error)
            self.settings_notice.set(self._test_notice)
            self._sync_tutorial()
            return

        if getattr(self, "_test_notice", None) is not None:
            if self.settings_notice.get() == self._test_notice:
                self.settings_notice.set("")
            self._test_notice = None
        if getattr(self, "tutorial", None) is not None:
            self.tutorial.test_started(self._tutorial_context())
        if getattr(self, "customisation", None) is not None:
            self.customisation.test_started(self._tutorial_context())

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
        if getattr(self, "tutorial", None) is not None:
            self.tutorial.test_finished(self._tutorial_context())
        if getattr(self, "customisation", None) is not None:
            self.customisation.test_finished(self._tutorial_context())

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
        customisation = getattr(self, "customisation", None)
        if customisation is not None:
            cleanup_steps.append(customisation.skip)
        tutorial = getattr(self, "tutorial", None)
        if tutorial is not None:
            cleanup_steps.append(tutorial.skip)
            cleanup_steps.append(self.tutorial_highlighter.close)
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
