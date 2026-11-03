"""Real Tk guide checks with temporary settings and no native resources."""

from pathlib import Path
import sys
import tempfile
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from red_handed.core.monitoring import MonitoringController
from red_handed.core.settings import MonitoringSettings, ProtectionMode
from red_handed.core.system_state import MonitoringStatus
from red_handed.detection.camera import CameraManager
from red_handed.detection.person_detector import DetectionResult, PersonDetector
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
        self.camera.check_availability.return_value = True
        self.camera.open.return_value = True
        self.camera.read_frame.return_value = np.zeros((100, 200, 3), dtype=np.uint8)
        detector = Mock(spec=PersonDetector)
        detector.detect.return_value = DetectionResult(person_count=0)
        self.controller = MonitoringController(
            camera=self.camera, detector=detector
        )
        self.root = tk.Tk()
        self.root.withdraw()
        self.window = MainWindow(
            self.root, self.controller, settings_store=self.store, enable_hotkeys=False
        )
        self.window.protection.surface = Mock()
        self.window.protection.web_opener = Mock(ready=False, last_error=None)
        self.window.hotkeys = Mock()
        self.addCleanup(self.window.close)
        # Layout tests run the Tk event loop but must not probe real foreground apps.
        for name in ("_camera_check_job", "_foreground_job"):
            self.root.after_cancel(getattr(self.window, name))
            setattr(self.window, name, None)

    def make_live(self):
        self.window.retry_camera()
        with patch.object(self.window, "_schedule_next_frame"):
            self.window.start_monitoring()
            self.window._update_preview()
        # A stable synthetic image supports drag tests even with the root withdrawn.
        photo = tk.PhotoImage(master=self.root, width=200, height=100)
        self.window.preview.show_image(photo)
        self.window._sync_tutorial()

    def draw_zone(self):
        preview = self.window.preview
        cx, cy = preview.winfo_width() / 2, preview.winfo_height() / 2
        preview._press(SimpleNamespace(x=cx - 40, y=cy - 20))
        preview._drag(SimpleNamespace(x=cx + 40, y=cy + 20))
        preview._release(SimpleNamespace(x=cx + 40, y=cy + 20))

    def reach_protection(self):
        self.make_live()
        self.window.start_tutorial()
        self.window.show_calibration()
        self.window.tutorial.next()  # Keep the saved zone.
        self.window.show_protection()

    def reach_preview(self):
        self.reach_protection()
        self.window.tutorial.next()  # Keep current protection settings.
        self.window.show_home()

    def test_navigation_and_skip_preserve_draft_monitoring_and_settings(self):
        self.make_live()
        self.window.show_calibration()
        draft = PrivacyZone(0.2, 0.3, 0.4, 0.4)
        self.window.preview.draft_zone = draft
        before = self.store.path.read_bytes()
        state = self.controller.state.monitoring_status

        self.window.replay_tutorial_button.invoke()
        self.assertTrue(self.window.tutorial.active)
        self.assertIs(self.window.tutorial_highlighter.target, self.window.calibration.save_button)
        self.window.tutorial_view.back_button.invoke()
        self.assertIs(self.window.tutorial_highlighter.target, self.window.preview)
        self.window.tutorial_view.back_button.invoke()
        self.assertIs(self.window.tutorial_highlighter.target, self.window.zone_setup_button)
        self.window.tutorial_view.skip_button.invoke()

        self.assertIsNone(self.window.tutorial_highlighter.target)
        self.assertIsNone(self.window.tutorial_highlighter._job)
        self.assertFalse(self.window.tutorial_view.winfo_manager())
        self.assertEqual(self.window.preview.draft_zone, draft)
        self.assertEqual(self.controller.state.monitoring_status, state)
        self.assertEqual(self.store.path.read_bytes(), before)
        self.camera.release.assert_not_called()

    def test_home_entry_and_replay_close_without_claiming_setup_is_complete(self):
        self.make_live()
        self.window.guide_button.invoke()
        self.window.zone_setup_button.invoke()
        self.assertEqual(self.window.tutorial_view.next_button.cget("text"), "Keep this zone")
        self.window.tutorial_view.next_button.invoke()
        self.assertTrue(self.window.tutorial_view.next_button.instate(["disabled"]))
        self.window.protection_mode_button.invoke()
        self.window.tutorial_view.next_button.invoke()
        self.window.home_button.invoke()
        self.window.home_test_button.invoke()
        self.window.end_test_protection()
        self.assertEqual(self.window.tutorial_view.next_button.cget("text"), "Finish")
        self.window.tutorial_view.next_button.invoke()
        self.assertFalse(self.window.tutorial.active)
        self.assertEqual(self.window.guide_button.winfo_manager(), "grid")
        self.window.replay_tutorial_button.invoke()
        self.assertEqual(self.window.tutorial.index, 1)
        self.window.tutorial.skip()
        self.window.show_settings()
        self.assertFalse(self.window.guide_button.winfo_manager())

    def test_highlight_tracks_resize_without_covering_target_or_removing_bindings(self):
        target = self.window.retry_button
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
        self.window.tutorial.skip()
        self.root.update_idletasks()
        self.assertIn(original, target.bind("<Configure>"))
        self.assertTrue(all(
            not border.winfo_ismapped() for border in self.window.tutorial_highlighter._borders
        ))

    def test_save_and_guide_buttons_fit_at_minimum_window_size(self):
        self.make_live()
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

    def test_camera_gates_on_real_preview_and_guides_retry_after_failures(self):
        self.window.start_tutorial()
        self.assertIs(self.window.tutorial_highlighter.target, self.window.retry_button)
        self.window.tutorial_view.next_button.invoke()
        self.assertEqual(self.window.tutorial.index, 0)
        self.camera.check_availability.return_value = False
        self.camera.last_error = "Camera permission denied"
        self.window.retry_button.invoke()
        self.assertEqual(self.window.tutorial.index, 0)
        self.assertIn("permission", self.window.message_text.get())

        self.camera.check_availability.return_value = True
        self.camera.last_error = None
        self.window.retry_button.invoke()
        self.assertIs(self.window.tutorial_highlighter.target, self.window.start_button)
        self.camera.open.return_value = False
        self.window.start_button.invoke()
        self.assertEqual(self.window.tutorial.index, 0)
        self.assertIs(self.window.tutorial_highlighter.target, self.window.retry_button)

        self.camera.open.return_value = True
        self.window.retry_button.invoke()
        with patch.object(self.window, "_schedule_next_frame"):
            self.window.start_button.invoke()
            self.assertEqual(self.window.tutorial.index, 0)  # Active alone is insufficient.
            self.assertIs(self.window.tutorial_highlighter.target, self.window.preview)
            with patch("red_handed.ui.main_window.Image.fromarray", side_effect=ValueError("Bad frame")):
                self.window._update_preview()
            self.assertEqual(self.window.tutorial.index, 0)
            self.assertFalse(self.window.preview.has_image)
            self.assertIs(self.window.tutorial_highlighter.target, self.window.stop_button)
            self.window._update_preview()
        self.assertEqual(self.window.tutorial.index, 1)
        self.assertIs(self.window.tutorial_highlighter.target, self.window.zone_setup_button)

    def test_fresh_zone_waits_for_valid_gesture_and_successful_save(self):
        self.store.save(MonitoringSettings())
        self.controller.apply_settings(self.store.load())
        self.window.preview.saved_zone = None
        self.window.start_tutorial()
        self.make_live()
        self.window.zone_setup_button.invoke()
        self.assertEqual(self.window.tutorial.index, 2)
        self.window.tutorial_view.next_button.invoke()
        self.assertEqual(self.window.tutorial.index, 2)
        preview = self.window.preview
        cx, cy = preview.winfo_width() / 2, preview.winfo_height() / 2
        for start, end in (((cx, cy), (cx, cy)), ((cx - 150, cy), (cx, cy))):
            preview._press(SimpleNamespace(x=start[0], y=start[1]))
            preview._release(SimpleNamespace(x=end[0], y=end[1]))
            self.assertIsNone(preview.draft_zone)
            self.assertEqual(self.window.tutorial.index, 2)

        self.draw_zone()
        self.assertEqual(self.window.tutorial.index, 3)
        self.assertIs(self.window.tutorial_highlighter.target, self.window.calibration.save_button)
        self.window.tutorial_view.next_button.invoke()
        self.assertEqual(self.window.tutorial.index, 3)
        before = self.store.path.read_bytes()
        draft = preview.draft_zone
        with patch.object(self.store, "save", side_effect=OSError("Disk full")):
            self.window.calibration.save_button.invoke()
        self.assertEqual(self.window.tutorial.index, 3)
        self.assertEqual(preview.draft_zone, draft)
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertIn("not saved", self.window.tutorial_view.instruction.cget("text"))

        self.window.calibration.save_button.invoke()
        self.assertEqual(self.window.tutorial.index, 4)
        self.assertEqual(self.store.load().privacy_zone, draft)
        self.assertIsNone(preview.draft_zone)

    def test_keep_saved_zone_does_not_write_and_replacement_waits_for_save(self):
        self.make_live()
        self.window.start_tutorial()
        self.window.zone_setup_button.invoke()
        before = self.store.path.read_bytes()
        saved = self.controller.settings.privacy_zone
        self.assertEqual(self.window.tutorial.index, 2)
        self.window.tutorial_view.next_button.invoke()
        self.assertEqual(self.window.tutorial.index, 4)
        self.assertEqual(self.store.path.read_bytes(), before)

        self.window.tutorial.back()
        self.window.tutorial_view.redraw_button.invoke()
        self.assertIs(self.window.tutorial_highlighter.target, self.window.preview)
        self.assertTrue(self.window.tutorial_view.next_button.instate(["disabled"]))
        self.draw_zone()
        self.assertEqual(self.controller.settings.privacy_zone, saved)
        with patch.object(self.store, "save", side_effect=OSError("Disk full")):
            self.window.save_zone()
        self.assertEqual(self.window.tutorial.index, 3)
        self.assertEqual(self.controller.settings.privacy_zone, saved)
        self.window.discard_zone_draft()
        self.assertEqual(self.window.tutorial.index, 2)
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_tutorial_and_sidebar_navigation_do_not_silently_discard_drafts(self):
        self.make_live()
        self.window.show_calibration()
        self.window.start_tutorial()
        self.window.tutorial.redraw()
        self.draw_zone()
        draft = self.window.preview.draft_zone
        self.window.tutorial.back()
        self.window._sync_tutorial()
        self.assertEqual(self.window.tutorial.index, 2)
        self.window.tutorial.next()
        self.assertEqual(self.window.tutorial.index, 3)
        self.window.zone_setup_button.invoke()  # Reopening the same panel keeps its draft.
        for navigate in (self.window.show_home, self.window.show_protection,
                         self.window.show_settings, self.window.show_applications, self.window.show_history):
            navigate()
            self.assertEqual(self.window._current_view, "calibration")
            self.assertEqual(self.window.preview.draft_zone, draft)
        self.assertIn("has been kept", self.window.message_text.get())

    def test_camera_loss_restarts_camera_guidance_without_losing_saved_zone(self):
        self.make_live()
        self.window.start_tutorial()
        self.window.zone_setup_button.invoke()
        saved = self.controller.settings.privacy_zone
        before = self.store.path.read_bytes()
        self.camera.read_frame.return_value = None
        self.window._update_preview()
        self.assertEqual(self.window.tutorial.index, 0)
        self.assertIs(self.window.tutorial_highlighter.target, self.window.retry_button)
        self.assertIs(self.controller.state.monitoring_status, MonitoringStatus.INACTIVE)
        self.assertEqual(self.controller.settings.privacy_zone, saved)
        self.assertEqual(self.store.path.read_bytes(), before)
        self.camera.read_frame.return_value = np.zeros((100, 200, 3), dtype=np.uint8)
        self.make_live()
        self.assertEqual(self.window.tutorial.index, 2)

    def test_protection_changes_require_save_and_preserve_edits_on_back_or_navigation(self):
        self.reach_protection()
        view = self.window.protection_view
        before = self.store.path.read_bytes()
        view.mode.set(ProtectionMode.SCREEN_BLACKOUT.value)
        self.assertEqual(self.window.tutorial.index, 4)
        self.assertIs(self.window.tutorial_highlighter.target, view.save_button)
        self.assertTrue(self.window.tutorial_view.next_button.instate(["disabled"]))
        self.window.tutorial.next()
        self.assertEqual(self.window.tutorial.index, 4)
        for navigate in (self.window.show_home, self.window.show_calibration,
                         self.window.show_settings, self.window.show_applications, self.window.show_history):
            navigate()
            self.assertEqual(self.window._current_view, "protection")
            self.assertEqual(view.mode.get(), ProtectionMode.SCREEN_BLACKOUT.value)
        self.window.tutorial.back()
        self.assertEqual(view.mode.get(), ProtectionMode.SCREEN_BLACKOUT.value)
        self.window.tutorial.next()  # Keep the saved zone and return to mode selection.
        with patch.object(self.window.hotkeys, "prepare", side_effect=ValueError("Shortcut already in use")):
            view.save_button.invoke()
        self.assertEqual(self.window.tutorial.index, 4)
        self.assertIn("Shortcut already in use", view.feedback.get())
        self.assertEqual(self.store.path.read_bytes(), before)
        with patch.object(self.store, "save", side_effect=OSError("Disk full")):
            view.save_button.invoke()
        self.assertEqual(self.window.tutorial.index, 4)
        self.assertEqual(view.mode.get(), ProtectionMode.SCREEN_BLACKOUT.value)
        self.assertEqual(self.store.path.read_bytes(), before)
        view.save_button.invoke()
        self.assertEqual(self.window.tutorial.index, 5)
        self.assertEqual(self.store.load_protection().mode, ProtectionMode.SCREEN_BLACKOUT)

    def test_discarding_protection_edits_then_keeping_saved_settings_does_not_write(self):
        self.reach_protection()
        view = self.window.protection_view
        before = self.store.path.read_bytes()
        view.hotkey.set("not a shortcut")
        view.save_button.invoke()
        self.assertEqual(self.window.tutorial.index, 4)
        self.assertIsNotNone(view.save_error)
        view.discard_button.invoke()
        self.assertFalse(view.has_unsaved_changes)
        self.assertIsNone(view.save_error)
        self.window.tutorial_view.next_button.invoke()
        self.assertEqual(self.window.tutorial.index, 5)
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_preview_timer_and_early_dismissal_both_reach_honest_summary(self):
        self.reach_preview()
        with patch.object(self.root, "after", wraps=self.root.after) as after:
            self.window.home_test_button.invoke()
        after.assert_any_call(5000, self.window.end_test_protection)
        self.assertEqual(self.window.tutorial.index, 5)
        self.assertTrue(self.controller.state.test_protection_requested)
        self.assertTrue(self.window.tutorial_view.back_button.instate(["disabled"]))
        self.window.end_test_protection()  # The scheduled timeout uses this same callback.
        self.assertEqual(self.window.tutorial.index, 6)
        summary = self.window.tutorial_view.instruction.cget("text")
        self.assertIn("Preview showed Privacy Overlay", summary)
        self.assertIn("Mode: Privacy Overlay", summary)
        self.assertIn("Ctrl+Alt+P", summary)
        self.assertIn("Protection: Inactive", summary)
        self.assertIn("Waiting for valid detection", summary)
        self.assertFalse(self.controller.state.protection_active)
        self.assertIsNone(self.window._test_job)

        self.window.tutorial.back()
        self.window.home_test_button.invoke()
        self.window.toggle_manual()  # During a test this dismisses rather than activating manual protection.
        self.assertEqual(self.window.tutorial.index, 6)
        self.assertFalse(self.controller.state.manual_protection_requested)
        self.window.stop_monitoring()
        self.assertIn("Monitoring: inactive", self.window.tutorial_view.instruction.cget("text"))

    def test_surface_failure_does_not_complete_preview_and_can_be_retried(self):
        self.reach_preview()
        surface = self.window.protection.surface
        surface.show.side_effect = RuntimeError("Surface unavailable")
        self.window.home_test_button.invoke()
        self.assertFalse(self.controller.state.protection_active)
        self.window.end_test_protection()
        self.assertEqual(self.window.tutorial.index, 5)
        self.assertIn("did not complete", self.window.tutorial_view.instruction.cget("text"))
        self.assertIn("Surface unavailable", self.window.tutorial_view.instruction.cget("text"))
        surface.show.side_effect = None
        self.window.home_test_button.invoke()
        self.window.end_test_protection()
        self.assertEqual(self.window.tutorial.index, 6)

    def test_real_protection_blocks_or_interrupts_preview_and_is_never_cleared_by_it(self):
        self.reach_preview()
        self.window.protection.toggle_manual()
        self.window._refresh_protection()
        self.assertTrue(self.window.home_test_button.instate(["disabled"]))
        self.window.begin_test_protection()  # Core arbitration also rejects programmatic requests.
        self.assertTrue(self.controller.state.manual_protection_requested)
        self.assertEqual(self.window.tutorial.index, 5)
        self.window.toggle_manual()
        self.window.home_test_button.invoke()
        self.window.protection.set_automatic(True)
        self.window._refresh_protection()
        self.window.end_test_protection()
        self.assertTrue(self.controller.state.automatic_protection_requested)
        self.assertTrue(self.controller.state.protection_active)
        self.assertEqual(self.window.tutorial.index, 5)
        self.window.tutorial.skip()
        self.assertTrue(self.controller.state.protection_active)

    def test_decoy_unavailable_records_overlay_fallback_and_ready_decoy_records_browser(self):
        self.reach_protection()
        view = self.window.protection_view
        view.mode.set(ProtectionMode.DECOY_WEBSITE.value)
        view.save_button.invoke()
        self.window.show_home()
        browser = self.window.protection.web_opener
        browser.last_error = "Chrome unavailable"
        self.window.home_test_button.invoke()
        self.assertEqual(self.window.protection.active_mode, ProtectionMode.PRIVACY_OVERLAY)
        self.window.end_test_protection()
        self.assertEqual(self.window.tutorial.index, 6)
        self.assertIn("Privacy Overlay (fallback for Decoy Website)",
                      self.window.tutorial_view.instruction.cget("text"))
        self.window.tutorial.back()
        browser.ready = True
        browser.last_error = None
        self.window.home_test_button.invoke()
        self.window.end_test_protection()
        self.assertIn("Preview showed Decoy Website.", self.window.tutorial_view.instruction.cget("text"))

    def test_protection_preview_and_summary_controls_fit_minimum_size(self):
        self.reach_protection()
        self.root.deiconify()
        self.root.geometry("940x800")
        self.root.update()
        for widget in (self.window.protection_view.save_button, self.window.protection_view.discard_button,
                       self.window.tutorial_view.next_button, self.window.tutorial_view.skip_button):
            right = widget.winfo_rootx() - self.root.winfo_rootx() + widget.winfo_width()
            bottom = widget.winfo_rooty() - self.root.winfo_rooty() + widget.winfo_height()
            self.assertLessEqual(right, self.root.winfo_width())
            self.assertLessEqual(bottom, self.root.winfo_height())
        self.window.tutorial.next()
        self.window.show_home()
        self.root.update()
        self.assertTrue(self.window.home_test_button.winfo_ismapped())
        self.window.home_test_button.invoke()
        self.window.end_test_protection()
        self.root.update()
        self.assertGreater(self.window.preview.winfo_height(), 80)


if __name__ == "__main__":
    unittest.main()
