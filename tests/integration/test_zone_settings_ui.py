"""Settings/UI integration using temporary files and mocked camera access."""

from red_handed.ui.main_window import MainWindow
from red_handed.ui.calibration_view import detection_labels
from red_handed.storage.settings_store import SettingsStore
from red_handed.detection.privacy_zone import PrivacyZone
from red_handed.detection.person_detector import DetectionResult, PersonDetector
from red_handed.detection.camera import CameraManager
from red_handed.core.settings import MonitoringSettings, Sensitivity
from red_handed.core.monitoring import MonitoringController
from pathlib import Path
import sys
import tempfile
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))


class ZoneSettingsUITests(unittest.TestCase):
    def setUp(self) -> None:
        # Never write to the user's real settings file during these tests.
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "settings.json"

        self.original = MonitoringSettings(
            privacy_zone=PrivacyZone(0.1, 0.1, 0.3, 0.4),
            sensitivity=Sensitivity.HIGH,
            activation_delay=1.5,
            recovery_delay=2.5,
        )
        SettingsStore(self.path).save(self.original)
        self.new_zone = PrivacyZone(0.6, 0.0, 0.4, 1.0)

        self.window = self.make_window()

    def make_window(self) -> MainWindow:
        """Create real Tk widgets without opening a camera or starting a loop."""
        camera = Mock(spec=CameraManager)
        camera.open.return_value = True
        camera.last_error = None
        detector = Mock(spec=PersonDetector)

        controller = MonitoringController(camera=camera, detector=detector)
        root = tk.Tk()
        root.withdraw()

        window = MainWindow(
            root,
            controller,
            settings_store=SettingsStore(self.path),
            enable_hotkeys=False,
        )

        def cleanup_window():
            try:
                exists = root.winfo_exists()
            except tk.TclError:
                return

            if exists:
                window.close()

        self.addCleanup(cleanup_window)
        return window

    def prepare_draft(self) -> None:
        """Simulate a completed drawing during active calibration."""
        self.window.controller.start_monitoring()
        self.window.show_calibration()
        self.window.preview.draft_zone = self.new_zone
        self.window._refresh_controls()

    def test_startup_loads_saved_zone(self) -> None:
        self.assertEqual(
            self.window.controller.settings,
            self.original,
        )
        self.assertEqual(
            self.window.preview.saved_zone,
            self.original.privacy_zone,
        )

    def test_save_preserves_other_settings_and_survives_restart(self) -> None:
        self.prepare_draft()
        self.assertFalse(
            self.window.calibration.save_button.instate(["disabled"]))

        self.window.calibration.save_button.invoke()

        saved = SettingsStore(self.path).load()
        self.assertEqual(saved.privacy_zone, self.new_zone)
        self.assertEqual(saved.sensitivity, Sensitivity.HIGH)
        self.assertEqual(saved.activation_delay, 1.5)
        self.assertEqual(saved.recovery_delay, 2.5)
        self.assertIsNone(self.window.preview.draft_zone)
        self.assertEqual(self.window.controller.settings, saved)

        # A newly constructed window must restore the same persisted settings.
        self.window.close()
        restarted = self.make_window()
        self.assertEqual(restarted.controller.settings, saved)
        self.assertEqual(restarted.preview.saved_zone, self.new_zone)

    def test_failed_save_keeps_old_zone_and_unsaved_draft(self) -> None:
        self.prepare_draft()
        before = self.path.read_bytes()

        with patch.object(
            self.window.settings_store,
            "save",
            side_effect=OSError("Disk is full."),
        ):
            self.window.save_zone()

        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.window.controller.settings, self.original)
        self.assertEqual(
            self.window.preview.saved_zone,
            self.original.privacy_zone,
        )
        self.assertEqual(self.window.preview.draft_zone, self.new_zone)

        # The next frame's status refresh must not erase the save error.
        self.window._refresh_status()
        self.assertIn("Zone not saved", self.window.message_text.get())

    def test_discard_and_home_do_not_save_drafts(self) -> None:
        before = self.path.read_bytes()

        self.prepare_draft()
        self.window.preview.discard_draft()
        self.assertIsNone(self.window.preview.draft_zone)

        self.prepare_draft()
        self.window.show_home()
        self.assertIsNone(self.window.preview.draft_zone)

        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.window.controller.settings, self.original)

    def test_save_without_draft_does_not_write(self) -> None:
        before = self.path.read_bytes()

        self.window.save_zone()

        self.assertEqual(self.path.read_bytes(), before)
        self.assertIn("Draw a non-empty", self.window.message_text.get())

    def test_malformed_settings_are_preserved_and_reported(self) -> None:
        self.window.close()
        self.path.write_text("not valid json", encoding="utf-8")

        restarted = self.make_window()
        restarted._refresh_status()

        self.assertEqual(restarted.controller.settings, MonitoringSettings())
        self.assertEqual(self.path.read_text(
            encoding="utf-8"), "not valid json")
        self.assertIn("could not be loaded", restarted.settings_notice.get())
        self.assertIn(
            "Privacy Zone: Unconfigured",
            restarted.risk_text.get(),
        )

    def test_calibration_helper_reads_shared_detection_state(self) -> None:
        self.window.controller.start_monitoring()
        self.window.controller.state.detection = DetectionResult(
            person_count=2)

        count, description = detection_labels(self.window.controller.state)

        self.assertEqual(count, "2")
        self.assertEqual(description, "Additional person detected")


if __name__ == "__main__":
    unittest.main()
