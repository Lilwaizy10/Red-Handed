"""Guide navigation is independent of camera, protection, and persistence."""

from pathlib import Path
from dataclasses import replace
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from red_handed.ui.tutorial_controller import TutorialContext, TutorialController


class TutorialControllerTests(unittest.TestCase):
    def setUp(self):
        self.show = Mock()
        self.hide = Mock()
        self.guide = TutorialController(self.show, self.hide)
        self.live = TutorialContext(camera_available=True, monitoring=True, preview_ready=True)

    def test_start_back_and_next_stay_within_steps(self):
        self.guide.back()
        self.guide.next()
        self.show.assert_not_called()
        self.assertFalse(self.guide.active)

        self.guide.start()
        self.guide.back()
        self.assertEqual(self.guide.index, 0)
        self.guide.next()
        self.assertEqual(self.guide.index, 0)  # Clicking Next cannot bypass camera setup.
        self.guide.update(self.live)
        self.assertEqual(self.guide.index, 1)
        self.guide.back()
        self.assertEqual(self.guide.index, 0)
        self.guide.update(self.live)
        self.assertEqual(self.guide.index, 0)  # Reviewing Back is stable across frames.
        self.guide.next()
        self.assertEqual(self.guide.index, 1)

    def test_skip_is_idempotent_and_replay_starts_at_first_step(self):
        self.guide.start()
        self.guide.next()
        self.guide.skip()
        self.guide.skip()
        self.hide.assert_called_once_with()
        self.assertFalse(self.guide.active)

        self.guide.start()
        self.assertTrue(self.guide.active)
        self.assertEqual(self.guide.index, 0)

    def test_saved_zone_requires_explicit_choice_before_closing(self):
        context = replace(self.live, zone_open=True, saved_zone=True)
        self.guide.start(context)
        self.assertEqual(self.guide.index, 2)
        self.assertEqual(self.show.call_args.args[0].next_label, "Keep this zone")
        self.guide.next()
        self.assertEqual(self.guide.index, 4)
        self.guide.next()
        self.assertTrue(self.guide.active)
        self.assertEqual(self.guide.index, 4)  # Protection settings have not been confirmed.
        context = replace(context, protection_open=True)
        self.guide.update(context)
        self.guide.next()
        self.assertEqual(self.guide.index, 5)
        self.guide.test_started(replace(context, test_requested=True, protection_active=True,
                                        actual_mode="Privacy Overlay"))
        self.guide.test_finished(context)
        self.assertEqual(self.guide.index, 6)
        self.guide.next()
        self.assertFalse(self.guide.active)
        self.hide.assert_called_once_with()

    def test_preview_failure_interruption_and_stale_test_cannot_complete_guide(self):
        context = replace(self.live, zone_open=True, saved_zone=True, protection_open=True)
        self.guide.start(context)
        self.guide.next()
        self.guide.next()
        failed = replace(context, test_requested=True, protection_error="Surface failed")
        self.guide.test_started(failed)
        self.guide.test_finished(context)
        self.assertEqual(self.guide.index, 5)

        shown = replace(context, test_requested=True, protection_active=True, actual_mode="Privacy Overlay")
        self.guide.test_started(shown)
        self.guide.update(replace(shown, test_requested=False, automatic_requested=True))
        self.guide.test_finished(context)
        self.assertEqual(self.guide.index, 5)

        self.guide.skip()
        self.guide.start(shown)
        self.guide.next()
        self.guide.next()
        self.guide.test_finished(context)  # An old preview from before replay is not counted.
        self.assertEqual(self.guide.index, 5)

    def test_fallback_summary_records_actual_mode_and_current_runtime(self):
        context = replace(self.live, zone_open=True, saved_zone=True, protection_open=True,
                          selected_mode="Decoy Website", runtime_summary="Monitoring: inactive. Protection: Inactive.")
        self.guide.start(context)
        self.guide.next()
        self.guide.next()
        self.guide.test_started(replace(context, test_requested=True, protection_active=True,
                                        actual_mode="Privacy Overlay"))
        self.guide.test_finished(context)
        summary = self.show.call_args.args[0].instruction
        self.assertIn("Privacy Overlay (fallback for Decoy Website)", summary)
        self.assertIn("Monitoring: inactive. Protection: Inactive.", summary)
        self.guide.update(replace(context, runtime_summary="Protection: Privacy Overlay (Manual)."))
        self.assertIn("(Manual)", self.show.call_args.args[0].instruction)

    def test_unsaved_protection_settings_block_keep_and_invalidate_old_preview(self):
        context = replace(self.live, zone_open=True, saved_zone=True, protection_open=True)
        self.guide.start(context)
        self.guide.next()
        self.guide.update(replace(context, protection_dirty=True))
        self.guide.next()
        self.assertEqual(self.guide.index, 4)
        self.guide.protection_saved(context)
        self.assertEqual(self.guide.index, 5)
        self.guide.update(replace(context, protection_dirty=True))
        self.assertEqual(self.guide.index, 4)

    def test_save_step_requires_success_event_not_existing_saved_zone(self):
        context = replace(self.live, zone_open=True, saved_zone=True)
        self.guide.start(context)
        self.guide.redraw()
        self.guide.next()
        self.assertEqual(self.guide.index, 2)
        draft = replace(context, draft_ready=True)
        self.guide.update(draft)
        self.assertEqual(self.guide.index, 3)
        self.guide.save_failed()
        self.guide.next()
        self.assertEqual(self.guide.index, 3)
        self.guide.update(context)  # Discarding a draft is not a successful save.
        self.assertEqual(self.guide.index, 2)
        self.guide.update(draft)
        self.guide.zone_saved(context)
        self.assertEqual(self.guide.index, 4)

    def test_back_from_save_preserves_need_to_save_and_repeated_frames_do_not_rerender(self):
        context = replace(self.live, zone_open=True, draft_ready=True)
        self.guide.start(context)
        self.assertEqual(self.guide.index, 3)
        self.guide.back()
        self.assertEqual(self.guide.index, 2)
        calls = self.show.call_count
        self.guide.update(context)
        self.guide.update(context)
        self.assertEqual(self.show.call_count, calls)
        self.guide.next()
        self.assertEqual(self.guide.index, 3)

    def test_camera_or_panel_loss_returns_to_required_step(self):
        context = replace(self.live, zone_open=True, draft_ready=True)
        self.guide.start(context)
        self.guide.update(replace(context, zone_open=False))
        self.assertEqual(self.guide.index, 1)
        self.guide.update(replace(context, camera_available=False, monitoring=False, preview_ready=False))
        self.assertEqual(self.guide.index, 0)
        self.assertEqual(self.show.call_args.args[0].target, "retry_camera")


if __name__ == "__main__":
    unittest.main()
