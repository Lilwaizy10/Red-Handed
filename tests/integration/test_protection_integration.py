"""Protection integration without covering the screen or registering real keys."""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from monitoring_test_support import (
    FakeClock,
    FakeFrame,
    ImmediateExecutor,
    read_detection,
)

from red_handed.core.monitoring import MonitoringController
from red_handed.core.protection import ProtectionManager
from red_handed.core.settings import (
    MonitoringSettings,
    ProtectionMode,
    ProtectionSettings,
)
from red_handed.detection.camera import CameraManager
from red_handed.detection.person_detector import DetectionResult, PersonDetector
from red_handed.detection.privacy_zone import PrivacyZone
from red_handed.storage.settings_store import SettingsStore
from red_handed.system.hotkey_manager import HotkeyManager
from red_handed.ui.main_window import MainWindow


class FakeHotkeyBackend:
    """Record registrations and let tests inject shortcut events."""

    def __init__(self):
        self.bindings = {}
        self.events = []
        self.reject = False
        self.closed = False

    def register(self, identifier, spec):
        if self.reject:
            return False
        self.bindings[identifier] = spec
        return True

    def unregister(self, identifier):
        self.bindings.pop(identifier, None)
        return True

    def drain(self):
        events, self.events = self.events, []
        return events

    def close(self):
        self.closed = True
        self.bindings.clear()


class ProtectionIntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "settings.json"
        self.store = SettingsStore(self.path)

        self.settings = MonitoringSettings(
            privacy_zone=PrivacyZone(0.6, 0.0, 0.4, 1.0),
            activation_delay=0.0,
            recovery_delay=0.5,
        )
        self.original_protection = ProtectionSettings()
        self.store.save(
            self.settings,
            protection=self.original_protection,
        )

        self.clock = FakeClock()
        self.camera = Mock(spec=CameraManager)
        self.camera.open.return_value = True
        self.camera.last_error = None
        self.camera.read_frame.return_value = FakeFrame()
        self.detector = Mock(spec=PersonDetector)

        self.controller = MonitoringController(
            camera=self.camera,
            detector=self.detector,
            settings=self.settings,
            clock=self.clock,
            executor=ImmediateExecutor(),
        )
        self.surface = Mock()
        self.manager = ProtectionManager(
            self.controller.state,
            self.surface,
        )
        self.controller.attach_protection(self.manager)

        # Construct only the dependencies needed by the window's coordinator
        # methods. No Tk widgets, desktop windows, or native services are created.
        self.window = MainWindow.__new__(MainWindow)
        self.window.root = Mock()
        self.window.root.after.return_value = "scheduled-job"
        self.window.controller = self.controller
        self.window.settings_store = self.store
        self.window.protection_settings = self.original_protection
        self.window.surface = self.surface
        self.window.protection = self.manager
        self.window.protection_text = Mock()
        self.window.hotkey_text = Mock()
        self.window.settings_notice = Mock()

        self.window._closed = False
        self.window._enable_hotkeys = True
        self.window._hotkey_error = None
        self.window._hotkey_job = None
        self.window._test_job = None
        self.window._frame_job = None
        self.window._camera_check_job = None

        self.backend = FakeHotkeyBackend()
        self.window.hotkeys = HotkeyManager(
            self.backend,
            self.window.toggle_manual,
        )
        self.window.hotkeys.configure(self.original_protection.hotkey)
        self.addCleanup(self.window.close)

    def observe(self, inside):
        """Publish a real controller observation using mocked face boxes."""
        self.controller.start_monitoring()
        additional = (
            (140, 20, 20, 20) if inside else (100, 20, 10, 10)
        )
        self.detector.detect.return_value = DetectionResult(
            person_count=2,
            bounding_boxes=((0, 0, 100, 100), additional),
        )
        read_detection(self.controller, self.clock)

    def test_risk_activates_surface_and_recovery_hides_it(self):
        self.observe(True)
        self.assertTrue(self.controller.state.protection_active)
        self.assertTrue(self.controller.state.automatic_protection_requested)

        self.observe(False)
        self.assertTrue(self.controller.state.protection_active)
        self.observe(False)
        self.assertTrue(self.controller.state.protection_active)
        self.observe(False)

        self.assertFalse(self.controller.state.protection_active)
        self.surface.hide.assert_called()

    def test_manual_request_survives_automatic_recovery(self):
        self.observe(True)
        self.window.toggle_manual()

        for _ in range(3):
            self.observe(False)

        self.assertFalse(self.controller.state.automatic_protection_requested)
        self.assertTrue(self.controller.state.manual_protection_requested)
        self.assertTrue(self.controller.state.protection_active)

        self.window.toggle_manual()
        self.assertFalse(self.controller.state.protection_active)

    def test_explicit_stop_preserves_manual_request(self):
        self.observe(True)
        self.window.toggle_manual()

        self.controller.stop_monitoring()

        self.assertFalse(self.controller.state.automatic_protection_requested)
        self.assertTrue(self.controller.state.manual_protection_requested)
        self.assertTrue(self.controller.state.protection_active)

    def test_camera_loss_retains_automatic_protection_until_explicit_stop(self):
        self.observe(True)
        self.camera.read_frame.return_value = None
        self.controller.read_frame()

        self.assertIsNone(self.controller.state.risk_status)
        self.assertTrue(self.controller.state.automatic_protection_requested)
        self.assertTrue(self.controller.state.protection_active)

        self.controller.stop_monitoring()
        self.assertFalse(self.controller.state.protection_active)

    def test_hotkey_works_without_monitoring(self):
        identifier = next(iter(self.backend.bindings))
        self.backend.events.append(identifier)

        self.window._poll_hotkeys()

        self.assertTrue(self.controller.state.manual_protection_requested)
        self.assertTrue(self.controller.state.protection_active)
        self.camera.open.assert_not_called()

    def test_test_timeout_does_not_clear_real_automatic_protection(self):
        self.window.begin_test_protection()
        self.assertTrue(self.controller.state.test_protection_requested)

        delay, timeout_callback = self.window.root.after.call_args.args
        self.assertEqual(delay, 5000)

        # Real risk replaces test mode before the timeout occurs.
        self.observe(True)
        self.assertFalse(self.controller.state.test_protection_requested)

        timeout_callback()

        self.assertTrue(self.controller.state.automatic_protection_requested)
        self.assertTrue(self.controller.state.protection_active)

    def test_test_timeout_clears_test_when_no_real_request_exists(self):
        self.window.begin_test_protection()
        timeout_callback = self.window.root.after.call_args.args[1]

        timeout_callback()

        self.assertFalse(self.controller.state.test_protection_requested)
        self.assertFalse(self.controller.state.protection_active)

    def test_conflicting_hotkey_preserves_file_and_old_binding(self):
        before = self.path.read_bytes()
        bindings = dict(self.backend.bindings)
        self.backend.reject = True

        candidate = ProtectionSettings(
            ProtectionMode.SCREEN_BLACKOUT,
            "Ctrl+Alt+O",
        )
        with self.assertRaises(ValueError):
            self.window.save_protection_settings(candidate)

        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.backend.bindings, bindings)
        self.assertEqual(
            self.window.protection_settings,
            self.original_protection,
        )

    def test_failed_save_rolls_back_candidate_hotkey(self):
        bindings = dict(self.backend.bindings)
        candidate = ProtectionSettings(
            ProtectionMode.SCREEN_BLACKOUT,
            "Ctrl+Alt+O",
        )

        with patch.object(
            self.store,
            "save",
            side_effect=OSError("Disk full."),
        ):
            with self.assertRaises(OSError):
                self.window.save_protection_settings(candidate)

        self.assertEqual(self.backend.bindings, bindings)
        self.assertEqual(
            self.window.hotkeys.current.text,
            self.original_protection.hotkey,
        )
        self.assertEqual(
            self.controller.state.selected_protection_mode,
            ProtectionMode.PRIVACY_OVERLAY,
        )

    def test_successful_save_preserves_monitoring_settings(self):
        candidate = ProtectionSettings(
            ProtectionMode.SCREEN_BLACKOUT,
            "Ctrl+Alt+O",
        )

        self.window.save_protection_settings(candidate)

        reloaded = SettingsStore(self.path)
        self.assertEqual(reloaded.load(), self.settings)
        self.assertEqual(reloaded.protection_settings, candidate)
        self.assertEqual(self.window.hotkeys.current.text, "Ctrl+Alt+O")
        self.assertEqual(len(self.backend.bindings), 1)
        self.assertEqual(
            self.controller.state.selected_protection_mode,
            ProtectionMode.SCREEN_BLACKOUT,
        )

    def test_close_attempts_remaining_cleanup_after_surface_failure(self):
        self.surface.close.side_effect = RuntimeError("Surface cleanup failed.")

        with self.assertLogs(
            "red_handed.ui.main_window",
            level="ERROR",
        ):
            self.window.close()

        self.assertTrue(self.backend.closed)
        self.window.root.destroy.assert_called_once()
        self.detector.close.assert_called_once()

        # A second call must not repeat cleanup.
        self.window.close()
        self.surface.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()