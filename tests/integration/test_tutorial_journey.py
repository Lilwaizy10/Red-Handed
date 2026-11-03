"""Connected guide journeys through Tk callbacks and real temporary stores.

Camera, detector, native hotkey backend, foreground lookup, browser and screen
surface are faked. Tk still registers each timer normally; tests dispatch those
registered commands explicitly so a five-second preview requires no sleeps.
"""

from pathlib import Path
import sys
import tempfile
from time import perf_counter
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock, patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from monitoring_test_support import ImmediateExecutor
from red_handed.core.applications import ActiveApplication, ApplicationSettings, ProtectedApplication
from red_handed.core.monitoring import MonitoringController
from red_handed.core.settings import MonitoringSettings, ProtectionMode, ProtectionSettings
from red_handed.core.system_state import MonitoringStatus
from red_handed.detection.camera import CameraManager
from red_handed.detection.person_detector import DetectionResult, PersonDetector
from red_handed.detection.privacy_zone import PrivacyZone
from red_handed.storage.settings_store import SettingsStore
from red_handed.ui.main_window import MainWindow


class TutorialJourneyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = SettingsStore(Path(temporary.name) / "settings.json")

    def create_window(self):
        root = tk.Tk()
        root.withdraw()
        real_after = root.after
        timers = {}

        def schedule(delay, callback=None, *args):
            # Leave layout/highlight idle callbacks alone, but hold timed work
            # until fire_timer dispatches its actual Tcl-registered callback.
            held_delay = 60_000 if isinstance(delay, int) and callback is not None else delay
            job = real_after(held_delay, callback, *args)
            if isinstance(delay, int) and callback is not None:
                timers[job] = delay
            return job

        scheduler = patch.object(root, "after", side_effect=schedule)
        scheduler.start()
        self.addCleanup(scheduler.stop)
        backend = Mock(register=Mock(return_value=True), drain=Mock(return_value=[]))
        camera = Mock(spec=CameraManager)
        camera.last_error = None
        camera.check_availability.return_value = True
        camera.open.return_value = True
        camera.read_frame.return_value = np.zeros((100, 200, 3), dtype=np.uint8)
        detector = Mock(spec=PersonDetector)
        detector.detect.return_value = DetectionResult(person_count=0)
        controller = MonitoringController(camera=camera, detector=detector, executor=ImmediateExecutor())
        surface = Mock()
        browser = Mock(ready=False, last_error=None)
        with (
            patch("red_handed.ui.main_window.WindowsHotkeyBackend", return_value=backend),
            patch("red_handed.ui.main_window.TkProtectionSurface", return_value=surface),
            patch("red_handed.ui.main_window.StaticWebOpener", return_value=browser),
        ):
            window = MainWindow(root, controller, settings_store=self.store)
        self.addCleanup(window.close)
        window._foreground_detector = Mock()
        window._foreground_detector.detect.return_value = ActiveApplication(error="Test foreground")
        root.deiconify()
        root.update()
        self.root, self.window, self.camera, self.backend = root, window, camera, backend
        self.surface, self.browser, self.timers = surface, browser, timers

    def fire_timer(self, job):
        command, kind = self.root.tk.call("after", "info", job)
        self.assertEqual(kind, "timer")
        # Cancel the Tcl event without deleting its Python command, then dispatch
        # it once. Tk's normal wrapper removes the command after it returns.
        self.root.tk.call("after", "cancel", job)
        self.root.tk.call(command)
        self.root.update_idletasks()

    def assert_step(self, title):
        self.assertIn(title, self.window.tutorial_view.progress.cget("text"))

    def start_camera(self):
        self.fire_timer(self.window._camera_check_job)
        self.window.start_button.invoke()
        self.assert_step("Start the camera")  # An open camera alone is insufficient.
        self.fire_timer(self.window._frame_job)
        self.assertTrue(self.window.preview.has_image)
        self.assert_step("Open zone setup")

    def draw_zone(self):
        self.root.update_idletasks()
        preview = self.window.preview
        cx, cy = preview.winfo_width() // 2, preview.winfo_height() // 2
        preview.event_generate("<ButtonPress-1>", x=cx - 40, y=cy - 20, when="now")
        preview.event_generate("<B1-Motion>", x=cx + 40, y=cy + 20, state=0x100, when="now")
        preview.event_generate("<ButtonRelease-1>", x=cx + 40, y=cy + 20, when="now")
        self.assertIsNotNone(preview.draft_zone)
        self.assert_step("Save your zone")

    def choose_protection(self, mode, hotkey="Ctrl+Alt+O"):
        view = self.window.protection_view
        radio = next(widget for widget in view.winfo_children()
                     if isinstance(widget, ttk.Radiobutton) and widget.cget("value") == mode.value)
        radio.invoke()
        entry = next(widget for widget in view.winfo_children() if isinstance(widget, ttk.Entry))
        entry.delete(0, tk.END)
        entry.insert(0, hotkey)

    def use_saved_setup(self):
        self.window.guide_button.invoke()
        self.start_camera()
        self.window.zone_setup_button.invoke()
        self.assert_step("Use your saved zone")
        self.window.tutorial_view.next_button.invoke()
        self.window.protection_mode_button.invoke()
        self.window.tutorial_view.next_button.invoke()
        self.window.home_button.invoke()
        self.assert_step("Preview your protection")

    def preview_and_finish(self):
        self.window.home_test_button.invoke()
        self.assert_step("Preview your protection")
        self.assertTrue(self.window.controller.state.test_protection_requested)
        self.assertEqual(self.timers[self.window._test_job], 5000)
        self.fire_timer(self.window._test_job)
        self.assert_step("Setup walkthrough complete")
        self.assertFalse(self.window.controller.state.test_protection_requested)
        self.window.tutorial_view.next_button.invoke()
        self.assertFalse(self.window.tutorial.active)

    def test_fresh_install_completes_and_reloads_saved_zone_mode_and_shortcut(self):
        self.create_window()
        self.window.guide_button.invoke()
        self.assertFalse(self.store.path.exists())
        self.start_camera()
        self.window.zone_setup_button.invoke()
        self.assert_step("Draw your privacy zone")
        self.draw_zone()
        zone = self.window.preview.draft_zone
        self.window.calibration.save_button.invoke()
        self.window.protection_mode_button.invoke()
        self.choose_protection(ProtectionMode.SCREEN_BLACKOUT)
        self.window.protection_view.save_button.invoke()
        self.assert_step("Preview your protection")
        self.assertEqual(self.window.hotkeys.current.text, "Ctrl+Alt+O")
        saved_bytes = self.store.path.read_bytes()
        self.window.home_button.invoke()
        self.preview_and_finish()
        self.assertIn("Preview showed Screen Blackout", self.window.tutorial_view.instruction.cget("text"))
        self.assertEqual(self.store.path.read_bytes(), saved_bytes)
        self.assertIs(self.window.controller.state.monitoring_status, MonitoringStatus.ACTIVE)
        self.camera.release.assert_not_called()
        self.window.close()

        self.create_window()
        self.assertFalse(self.window.tutorial.active)
        self.assertEqual(self.window.preview.saved_zone, zone)
        self.assertEqual(self.window.protection_settings, ProtectionSettings(ProtectionMode.SCREEN_BLACKOUT, "Ctrl+Alt+O"))
        self.assertEqual(self.window.hotkeys.current.text, "Ctrl+Alt+O")
        self.assertEqual(self.store.path.read_bytes(), saved_bytes)
        self.window.replay_tutorial_button.invoke()
        self.assert_step("Start the camera")
        self.start_camera()
        self.window.zone_setup_button.invoke()
        self.assert_step("Use your saved zone")
        self.assertEqual(self.store.path.read_bytes(), saved_bytes)

    def test_existing_setup_completes_without_writes_and_reports_decoy_fallback_and_app_gate(self):
        settings = MonitoringSettings(privacy_zone=PrivacyZone(0.1, 0.2, 0.4, 0.5),
                                      activation_delay=1.25, recovery_delay=2.5)
        protection = ProtectionSettings(ProtectionMode.DECOY_WEBSITE, "Ctrl+Alt+O")
        applications = ApplicationSettings(True, (ProtectedApplication("Editor", r"C:\Apps\editor.exe"),))
        self.store.save(settings, protection=protection, applications=applications)
        before = self.store.path.read_bytes()
        self.create_window()
        self.browser.last_error = "Chrome unavailable"
        self.use_saved_setup()
        self.preview_and_finish()
        summary = self.window.tutorial_view.instruction.cget("text")
        self.assertIn("Privacy Overlay (fallback for Decoy Website)", summary)
        self.assertIn("Selected-app restriction currently blocks automatic protection", summary)
        self.assertNotIn("check shortcut status", summary)
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertEqual(self.window.controller.settings, settings)
        self.assertEqual(self.window.application_settings, applications)
        self.assertEqual(self.window.protection_settings, protection)

    def test_failures_block_progress_until_camera_zone_shortcut_storage_and_preview_recover(self):
        self.create_window()
        self.window.guide_button.invoke()
        self.camera.check_availability.return_value = False
        self.fire_timer(self.window._camera_check_job)
        self.window.tutorial_view.next_button.invoke()
        self.assert_step("Start the camera")
        self.camera.check_availability.return_value = True
        self.window.retry_button.invoke()
        self.window.start_button.invoke()
        self.fire_timer(self.window._frame_job)
        self.window.zone_setup_button.invoke()
        self.window.calibration.save_button.invoke()
        self.assert_step("Draw your privacy zone")
        self.assertFalse(self.store.path.exists())
        self.draw_zone()
        with patch.object(self.store, "save", side_effect=OSError("Disk full")):
            self.window.calibration.save_button.invoke()
        self.assert_step("Save your zone")
        self.assertFalse(self.store.path.exists())
        self.window.calibration.save_button.invoke()
        self.window.protection_mode_button.invoke()
        self.choose_protection(ProtectionMode.SCREEN_BLACKOUT)
        before = self.store.path.read_bytes()
        self.backend.register.return_value = False
        self.window.protection_view.save_button.invoke()
        self.assert_step("Choose screen protection")
        self.assertEqual(self.window.hotkeys.current.text, "Ctrl+Alt+P")
        self.assertEqual(self.store.path.read_bytes(), before)
        self.backend.register.return_value = True
        with patch.object(self.store, "save", side_effect=OSError("Disk full")):
            self.window.protection_view.save_button.invoke()
        self.assert_step("Choose screen protection")
        self.assertEqual(self.window.hotkeys.current.text, "Ctrl+Alt+P")
        self.assertEqual(self.store.path.read_bytes(), before)
        self.window.protection_view.save_button.invoke()
        self.window.home_button.invoke()
        self.surface.show.side_effect = RuntimeError("Surface unavailable")
        self.window.home_test_button.invoke()
        self.fire_timer(self.window._test_job)
        self.assert_step("Preview your protection")
        self.assertIn("Surface unavailable", self.window.tutorial_view.instruction.cget("text"))
        self.surface.show.side_effect = None
        self.preview_and_finish()

    def test_skip_and_replay_keep_unsaved_zone_monitoring_and_real_protection(self):
        self.create_window()
        self.window.guide_button.invoke()
        self.start_camera()
        self.window.zone_setup_button.invoke()
        self.draw_zone()
        draft = self.window.preview.draft_zone
        self.window.emergency_button.invoke()
        self.assertTrue(self.window.controller.state.manual_protection_requested)
        self.window.tutorial_view.skip_button.invoke()
        self.assertEqual(self.window.preview.draft_zone, draft)
        self.assertIs(self.window.controller.state.monitoring_status, MonitoringStatus.ACTIVE)
        self.assertTrue(self.window.controller.state.protection_active)
        self.assertFalse(self.store.path.exists())
        self.window.replay_tutorial_button.invoke()
        self.assert_step("Save your zone")
        self.assertEqual(self.window.preview.draft_zone, draft)
        self.assertTrue(self.window.controller.state.manual_protection_requested)
        self.camera.open.assert_called_once_with()
        self.camera.release.assert_not_called()

    def test_replay_does_not_count_the_previous_preview_timeout(self):
        self.store.save(MonitoringSettings(privacy_zone=PrivacyZone(0.1, 0.1, 0.4, 0.5)))
        self.create_window()
        self.use_saved_setup()
        self.window.home_test_button.invoke()
        old_timeout = self.window._test_job
        self.window.tutorial_view.skip_button.invoke()
        self.assertTrue(self.window.controller.state.test_protection_requested)
        self.window.replay_tutorial_button.invoke()
        self.window.zone_setup_button.invoke()
        self.window.tutorial_view.next_button.invoke()
        self.window.protection_mode_button.invoke()
        self.window.tutorial_view.next_button.invoke()
        self.window.home_button.invoke()
        self.fire_timer(old_timeout)
        self.assert_step("Preview your protection")
        self.assertTrue(self.window.tutorial_view.next_button.instate(["disabled"]))
        self.preview_and_finish()
        self.camera.open.assert_called_once_with()

    def test_registered_shortcut_dismisses_preview_and_cancels_its_timeout(self):
        self.store.save(MonitoringSettings(privacy_zone=PrivacyZone(0.1, 0.1, 0.4, 0.5)))
        self.create_window()
        self.use_saved_setup()
        self.window.home_test_button.invoke()
        timeout = self.window._test_job
        identifier = self.backend.register.call_args.args[0]
        self.backend.drain.return_value = [(identifier, perf_counter())]
        self.fire_timer(self.window._hotkey_job)
        self.backend.drain.return_value = []
        self.assert_step("Setup walkthrough complete")
        self.assertFalse(self.window.controller.state.test_protection_requested)
        self.assertFalse(self.window.controller.state.manual_protection_requested)
        self.assertIsNone(self.window._test_job)
        self.assertNotIn(timeout, self.root.tk.splitlist(self.root.tk.call("after", "info")))

    def test_close_during_preview_cancels_all_app_callbacks_and_releases_resources(self):
        self.store.save(MonitoringSettings(privacy_zone=PrivacyZone(0.1, 0.1, 0.4, 0.5)))
        self.create_window()
        self.use_saved_setup()
        self.window.home_test_button.invoke()
        command, _ = self.root.tk.call("after", "info", self.window._test_job)
        pending = set(self.root.tk.splitlist(self.root.tk.call("after", "info")))
        self.assertTrue(pending.intersection(self.timers))
        self.window.close()
        self.assertFalse(self.window.tutorial.active)
        self.assertIsNone(self.window.tutorial_highlighter._job)
        self.assertIsNone(self.window.tutorial_highlighter._root_binding)
        remaining = set(self.root.tk.splitlist(self.root.tk.call("after", "info")))
        self.assertFalse(pending.intersection(remaining))
        self.assertFalse(self.root.tk.call("info", "commands", command))
        self.backend.close.assert_called_once_with()
        self.camera.release.assert_called_once_with()
        self.surface.close.assert_called_once_with()
        self.browser.shutdown.assert_called_once_with()
        self.assertFalse(self.root.tk.call("info", "commands", str(self.root)))


if __name__ == "__main__":
    unittest.main()
