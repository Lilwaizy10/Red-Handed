"""Real Tk guide checks with temporary settings and no native resources."""

from pathlib import Path
import sys
import tempfile
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from red_handed.core.monitoring import MonitoringController
from red_handed.core.settings import MonitoringSettings
from red_handed.detection.camera import CameraManager
from red_handed.detection.person_detector import PersonDetector
from red_handed.detection.privacy_zone import PrivacyZone
from red_handed.storage.settings_store import SettingsStore
from red_handed.ui.main_window import MainWindow


class TutorialUITests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = SettingsStore(Path(temporary.name) / "settings.json")
        self.store.save(MonitoringSettings(privacy_zone=PrivacyZone(0.1, 0.1, 0.4, 0.5)))
        self.camera = Mock(spec=CameraManager)
        self.camera.last_error = None
        self.controller = MonitoringController(
            camera=self.camera, detector=Mock(spec=PersonDetector)
        )
        self.root = tk.Tk()
        self.root.withdraw()
        self.window = MainWindow(
            self.root, self.controller, settings_store=self.store, enable_hotkeys=False
        )
        self.addCleanup(self.window.close)
        # Layout tests run the Tk event loop but must not probe real foreground apps.
        for name in ("_camera_check_job", "_foreground_job"):
            self.root.after_cancel(getattr(self.window, name))
            setattr(self.window, name, None)

    def test_navigation_and_skip_preserve_draft_monitoring_and_settings(self):
        self.window.show_calibration()
        draft = PrivacyZone(0.2, 0.3, 0.4, 0.4)
        self.window.preview.draft_zone = draft
        before = self.store.path.read_bytes()
        self.controller.start_monitoring()
        state = self.controller.state.monitoring_status

        self.window.replay_tutorial_button.invoke()
        self.assertTrue(self.window.tutorial.active)
        self.assertIs(self.window.tutorial_highlighter.target, self.window.start_button)
        self.assertTrue(self.window.tutorial_view.back_button.instate(["disabled"]))
        self.window.tutorial_view.next_button.invoke()
        self.assertIs(self.window.tutorial_highlighter.target, self.window.zone_setup_button)
        self.window.tutorial_view.back_button.invoke()
        self.assertEqual(self.window.tutorial.index, 0)
        self.window.tutorial_view.skip_button.invoke()

        self.assertIsNone(self.window.tutorial_highlighter.target)
        self.assertIsNone(self.window.tutorial_highlighter._job)
        self.assertFalse(self.window.tutorial_view.winfo_manager())
        self.assertEqual(self.window.preview.draft_zone, draft)
        self.assertEqual(self.controller.state.monitoring_status, state)
        self.assertEqual(self.store.path.read_bytes(), before)
        self.camera.release.assert_not_called()

    def test_home_entry_and_replay_close_without_claiming_setup_is_complete(self):
        self.window.guide_button.invoke()
        self.window.tutorial_view.next_button.invoke()
        self.window.tutorial_view.next_button.invoke()
        self.assertEqual(self.window.tutorial_view.next_button.cget("text"), "Close guide")
        self.window.tutorial_view.next_button.invoke()
        self.assertFalse(self.window.tutorial.active)
        self.assertEqual(self.window.guide_button.winfo_manager(), "grid")
        self.window.replay_tutorial_button.invoke()
        self.assertEqual(self.window.tutorial.index, 0)
        self.window.tutorial.skip()
        self.window.show_settings()
        self.assertFalse(self.window.guide_button.winfo_manager())

    def test_highlight_tracks_resize_without_covering_target_or_removing_bindings(self):
        target = self.window.start_button
        original = target.bind("<Configure>", lambda event: None, add="+")
        self.root.deiconify()
        self.window.start_tutorial()
        for width, height in ((940, 800), (1100, 900)):
            self.root.geometry(f"{width}x{height}")
            self.root.update()
            x = target.winfo_rootx() - self.root.winfo_rootx()
            y = target.winfo_rooty() - self.root.winfo_rooty()
            right, bottom = x + target.winfo_width(), y + target.winfo_height()
            top_border = self.window.tutorial_highlighter._borders[0]
            self.assertEqual((top_border.winfo_x(), top_border.winfo_y()), (x - 3, y - 3))
            for border in self.window.tutorial_highlighter._borders:
                self.assertTrue(border.winfo_ismapped())
                bx, by = border.winfo_x(), border.winfo_y()
                self.assertTrue(
                    bx + border.winfo_width() <= x or bx >= right
                    or by + border.winfo_height() <= y or by >= bottom
                )
            self.window.tutorial.next()
            self.window.tutorial.back()
        self.window.tutorial.skip()
        self.root.update_idletasks()
        self.assertIn(original, target.bind("<Configure>"))
        self.assertTrue(all(
            not border.winfo_ismapped() for border in self.window.tutorial_highlighter._borders
        ))

    def test_save_and_guide_buttons_fit_at_minimum_window_size(self):
        self.root.deiconify()
        self.root.geometry("940x800")
        self.window.start_tutorial()
        self.window.show_calibration()
        self.root.update()
        for widget in (
            self.window.calibration.save_button, self.window.tutorial_view.skip_button,
            self.window.tutorial_view.next_button,
        ):
            self.assertTrue(widget.winfo_ismapped())
            bottom = widget.winfo_rooty() - self.root.winfo_rooty() + widget.winfo_height()
            self.assertLessEqual(bottom, self.root.winfo_height())
        self.assertGreater(self.window.preview.winfo_height(), 80)

    def test_close_cancels_highlight_work_and_releases_bindings(self):
        self.window.start_tutorial()
        highlight = self.window.tutorial_highlighter
        self.assertIsNotNone(highlight._job)
        with patch.object(self.root, "after_cancel", wraps=self.root.after_cancel) as cancel:
            self.window.close()
        self.assertTrue(cancel.called)
        self.assertIsNone(highlight._job)
        self.assertIsNone(highlight.target)
        self.assertIsNone(highlight._root_binding)


if __name__ == "__main__":
    unittest.main()
