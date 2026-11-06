"""Final acceptance journeys through the real dashboard and core services.

Camera, detector, clock, native hotkey backend, browser and screen surface are
faked. Tk widgets, settings/history files, risk timing and protection
arbitration are real. Tk timers never run, so each test drives frames directly.
"""

from pathlib import Path
import sys
import tempfile
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from monitoring_test_support import FakeClock, ImmediateExecutor

from red_handed.core.events import EventAction, EventType
from red_handed.core.monitoring import MonitoringController
from red_handed.core.privacy_risk import RiskStatus
from red_handed.core.settings import MonitoringSettings, ProtectionMode
from red_handed.core.system_state import CameraStatus, MonitoringStatus
from red_handed.detection.camera import CameraManager
from red_handed.detection.person_detector import DetectionResult, PersonDetector
from red_handed.detection.privacy_zone import PrivacyZone
from red_handed.storage.event_store import EventStore
from red_handed.storage.settings_store import SettingsStore
from red_handed.ui.main_window import MainWindow


class FakeHotkeyBackend:
    """Accept registrations and let a test inject a global shortcut press."""

    def __init__(self):
        self.bindings = {}
        self.events = []

    def register(self, identifier, spec):
        self.bindings[identifier] = spec
        return True

    def unregister(self, identifier):
        self.bindings.pop(identifier, None)
        return True

    def drain(self):
        events, self.events = self.events, []
        return events

    def close(self):
        self.bindings.clear()


class AcceptanceScenarioTests(unittest.TestCase):
    ZONE = PrivacyZone(0.6, 0.0, 0.4, 1.0)

    def setUp(self):
        # Never touch the operator's real settings or history.
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "settings.json"
        self.clock = FakeClock()
        self.frame = np.zeros((100, 200, 3), dtype=np.uint8)

    def launch(self, zone=None):
        """Start the real window from saved settings, then run its camera check."""
        SettingsStore(self.path).save(
            MonitoringSettings(zone, activation_delay=0.5, recovery_delay=0.5)
        )

        self.camera = Mock(spec=CameraManager)
        self.camera.last_error = None
        self.camera.check_availability.return_value = True
        self.camera.open.return_value = True
        self.camera.read_frame.return_value = self.frame
        self.detector = Mock(spec=PersonDetector)
        self.surface = Mock(window=None)
        self.backend = FakeHotkeyBackend()

        controller = MonitoringController(
            camera=self.camera,
            detector=self.detector,
            clock=self.clock,
            executor=ImmediateExecutor(),
        )
        self.state = controller.state
        self.root = tk.Tk()
        self.root.withdraw()

        with (
            patch("red_handed.ui.main_window.WindowsHotkeyBackend", return_value=self.backend),
            patch("red_handed.ui.main_window.TkProtectionSurface", return_value=self.surface),
            patch("red_handed.ui.main_window.StaticWebOpener", return_value=Mock(
                ready=False, starting=False, last_error=None, browser_pid=None)),
        ):
            self.window = MainWindow(
                self.root, controller, settings_store=SettingsStore(self.path)
            )
        self.addCleanup(self.window.close)

        # This is the startup check that Tk would run after 100 ms.
        self.window.retry_camera()

    def tick(self):
        """Run the scheduled preview callback once without waiting for its timer."""
        job, self.window._frame_job = self.window._frame_job, None
        if job is not None:
            self.root.after_cancel(job)
        self.window._update_preview()

    def observe(self, inside):
        """Submit one frame, collect its detection, then advance capture time."""
        additional = (140, 20, 20, 20) if inside else (100, 20, 10, 10)
        self.detector.detect.return_value = DetectionResult(
            person_count=2,
            bounding_boxes=((0, 0, 100, 100), additional),
        )
        self.tick()
        self.tick()
        self.clock.now += 0.25

    def press_hotkey(self):
        """Dispatch one shortcut press through HotkeyManager on the Tk thread."""
        job, self.window._hotkey_job = self.window._hotkey_job, None
        if job is not None:
            self.root.after_cancel(job)
        self.backend.events.append(next(iter(self.backend.bindings)))
        self.window._poll_hotkeys()

    def lose_camera(self):
        self.camera.last_error = "Camera disconnected."
        self.camera.read_frame.return_value = None
        self.camera.check_availability.return_value = False

    def restore_camera(self):
        self.camera.last_error = None
        self.camera.read_frame.return_value = self.frame
        self.camera.check_availability.return_value = True

    def assert_enabled(self, button, enabled):
        self.assertEqual(button.instate(["!disabled"]), enabled)

    def assert_saved_events(self, *expected):
        """Check the history file, not only the recorder's in-memory copy."""
        self.window.recorder.flush()
        saved = EventStore(self.path.with_name("events.json")).load()
        self.assertEqual(
            [(event.event_type, event.action) for event in saved],
            list(expected),
        )

    def test_startup_zone_risk_protection_recovery_journey(self):
        # Startup: the camera is ready, but nothing has been opened yet.
        self.launch()
        self.assertEqual(self.window.camera_text.get(), "Available")
        self.assertEqual(self.window.monitoring_text.get(), "Inactive")
        self.assert_enabled(self.window.start_button, True)
        self.camera.open.assert_not_called()

        self.window.start_button.invoke()
        self.assertIs(self.state.monitoring_status, MonitoringStatus.ACTIVE)
        self.camera.open.assert_called_once()

        # Without a saved zone, a detected person cannot create risk.
        self.observe(True)
        self.assertEqual(self.window.people_text.get(), "2")
        self.assertTrue(self.window.preview.has_image)
        self.assertIsNone(self.state.risk_status)
        self.assertIn(
            "Unavailable (configure a privacy zone)",
            self.window.risk_text.get(),
        )
        self.surface.show.assert_not_called()

        # Zone: the saved rectangle is persisted and starts affecting risk.
        self.window.show_calibration()
        self.window.preview.draft_zone = self.ZONE
        self.window.calibration.save_button.invoke()
        self.assertTrue(self.window.show_home())
        self.assertEqual(self.window.preview.saved_zone, self.ZONE)
        self.assertEqual(SettingsStore(self.path).load().privacy_zone, self.ZONE)

        # Risk: protection waits for the full activation delay.
        for _ in range(2):
            self.observe(True)
            self.assertIs(self.state.risk_status, RiskStatus.PENDING_ACTIVATION)
            self.assertFalse(self.state.protection_active)

        # Protection: the third sample reaches 0.5 seconds.
        self.observe(True)
        self.assertIs(self.state.risk_status, RiskStatus.ACTIVE)
        self.assertTrue(self.state.automatic_protection_requested)
        self.assertTrue(self.state.protection_active)
        self.surface.show.assert_called_once_with(
            ProtectionMode.PRIVACY_OVERLAY, test=False, source="Automatic"
        )
        self.assertEqual(
            self.window.protection_text.get(),
            "Protection: Privacy Overlay (Automatic)",
        )

        # Recovery: the screen stays covered until the recovery delay completes.
        for _ in range(2):
            self.observe(False)
            self.assertIs(self.state.risk_status, RiskStatus.PENDING_RECOVERY)
            self.assertTrue(self.state.protection_active)

        self.observe(False)
        self.assertIs(self.state.risk_status, RiskStatus.INACTIVE)
        self.assertFalse(self.state.protection_active)
        self.surface.hide.assert_called_once()
        self.assertEqual(self.window.protection_text.get(), "Protection: Inactive")

        self.window.stop_button.invoke()
        self.assertIs(self.state.monitoring_status, MonitoringStatus.INACTIVE)
        self.camera.release.assert_called()
        self.assert_saved_events(
            (EventType.RISK_DETECTED, EventAction.RISK_ACTIVE),
            (EventType.AUTOMATIC_ACTIVATED, EventAction.PROTECTED),
            (EventType.AUTOMATIC_DEACTIVATED, EventAction.RESTORED),
        )

    def test_camera_failure_keeps_manual_protection_usable_until_recovery(self):
        # Reach real automatic protection before the camera fails.
        self.launch(self.ZONE)
        self.window.start_button.invoke()
        for _ in range(3):
            self.observe(True)
        self.assertTrue(self.state.automatic_protection_requested)

        # Failure: monitoring stops, and lost evidence never reveals the screen.
        self.lose_camera()
        self.tick()

        self.assertIs(self.state.monitoring_status, MonitoringStatus.INACTIVE)
        self.assertIs(self.state.camera_status, CameraStatus.UNAVAILABLE)
        self.assertIsNone(self.state.risk_status)
        self.assertEqual(self.window.people_text.get(), "--")
        self.assertEqual(self.window.message_text.get(), "Camera disconnected.")
        self.camera.release.assert_called()
        self.assertTrue(self.state.automatic_protection_requested)
        self.assertTrue(self.state.protection_active)
        self.assert_enabled(self.window.start_button, False)
        self.assert_enabled(self.window.stop_button, False)
        self.assert_enabled(self.window.retry_button, True)

        # Manual: the shortcut works without opening or probing the camera.
        opens, checks = (
            self.camera.open.call_count,
            self.camera.check_availability.call_count,
        )
        self.press_hotkey()
        self.assertTrue(self.state.manual_protection_requested)
        self.assertEqual(self.surface.show.call_args.kwargs["source"], "Automatic + Manual")
        self.assertEqual(self.camera.open.call_count, opens)
        self.assertEqual(self.camera.check_availability.call_count, checks)

        # The dashboard Stop button is disabled here, so the surface's own
        # Stop Monitoring / Clear Automatic control is the available path.
        self.window.stop_monitoring()
        self.assertFalse(self.state.automatic_protection_requested)
        self.assertTrue(self.state.manual_protection_requested)
        self.assertTrue(self.state.protection_active)
        self.assertEqual(self.surface.show.call_args.kwargs["source"], "Manual")
        self.surface.hide.assert_not_called()

        # A failed retry reports the error again without another event row.
        self.window.retry_button.invoke()
        self.assertIs(self.state.camera_status, CameraStatus.UNAVAILABLE)
        self.assertEqual(self.window.message_text.get(), "Camera disconnected.")

        # Recovery: a new session starts timing again and keeps the manual request.
        self.restore_camera()
        self.window.retry_button.invoke()
        self.assertIs(self.state.camera_status, CameraStatus.AVAILABLE)
        self.assert_enabled(self.window.start_button, True)

        self.window.start_button.invoke()
        self.observe(True)
        self.assertIs(self.state.risk_status, RiskStatus.PENDING_ACTIVATION)
        self.assertFalse(self.state.automatic_protection_requested)
        self.assertTrue(self.state.manual_protection_requested)
        self.assertTrue(self.state.protection_active)

        # Releasing the only remaining request restores the display.
        self.window.emergency_button.invoke()
        self.assertFalse(self.state.manual_protection_requested)
        self.assertFalse(self.state.protection_active)
        self.surface.hide.assert_called_once()

        self.window.stop_button.invoke()
        self.assert_saved_events(
            (EventType.RISK_DETECTED, EventAction.RISK_ACTIVE),
            (EventType.AUTOMATIC_ACTIVATED, EventAction.PROTECTED),
            (EventType.CAMERA_UNAVAILABLE, EventAction.CAMERA_UNAVAILABLE),
            (EventType.MANUAL_ACTIVATED, EventAction.STILL_PROTECTED),
            (EventType.AUTOMATIC_DEACTIVATED, EventAction.STILL_PROTECTED),
            (EventType.MANUAL_DEACTIVATED, EventAction.RESTORED),
        )


if __name__ == "__main__":
    unittest.main()