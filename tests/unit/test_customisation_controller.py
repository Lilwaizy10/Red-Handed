from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from red_handed.ui.customisation_controller import CustomisationContext, CustomisationController


class CustomisationControllerTests(unittest.TestCase):
    def setUp(self):
        self.show, self.hide = Mock(), Mock()
        self.guide = CustomisationController(self.show, self.hide)

    def test_timing_waits_for_save_and_needs_no_camera(self):
        context = CustomisationContext(timing_open=True)
        self.guide.start("timing", context)
        self.assertEqual(self.guide.index, 1)
        self.guide.next()
        self.guide.next()
        self.guide.update(replace(context, timing_error="Invalid delay"))
        self.guide.next()
        self.assertEqual(self.guide.index, 3)
        self.guide.saved("timing", replace(context, activation_delay=1.25, recovery_delay=2.5))
        self.assertEqual(self.guide.index, 4)
        self.assertIn("1.25", self.show.call_args.args[0].instruction)
        self.guide.next()
        self.assertFalse(self.guide.active)

    def test_enabled_empty_application_list_cannot_complete_guide(self):
        context = CustomisationContext(applications_open=True, applications_enabled=True)
        self.guide.start("applications", context)
        self.guide.next()
        self.guide.next()
        self.assertEqual(self.guide.index, 2)
        self.guide.saved("applications", replace(context, saved_applications_enabled=True))
        self.assertEqual(self.guide.index, 2)
        context = replace(context, applications_count=1, saved_applications_enabled=True, saved_applications_count=1)
        self.guide.application_added(context)
        self.assertEqual(self.guide.index, 3)
        self.guide.saved("applications", context)
        self.assertEqual(self.guide.index, 4)

    def test_shortcut_timeout_is_not_verification_but_real_dispatch_is(self):
        context = CustomisationContext(protection_open=True)
        self.guide.start("shortcut", context)
        self.guide.saved("shortcut", context)
        shown = replace(context, test_requested=True, protection_active=True, actual_mode="Privacy Overlay")
        self.guide.test_started(shown)
        self.guide.test_finished(context)
        self.assertEqual(self.guide.index, 2)
        self.guide.test_started(shown)
        self.guide.shortcut_used()
        self.guide.test_finished(context)
        self.assertEqual(self.guide.index, 3)
        self.assertIn("Verified", self.show.call_args.args[0].instruction)

    def test_shortcut_skip_is_explicit_and_real_protection_is_not_changed(self):
        context = CustomisationContext(protection_open=True, manual_requested=True, protection_active=True)
        self.guide.start("shortcut", context)
        self.guide.saved("shortcut", context)
        self.guide.next()
        self.assertIn("skipped", self.show.call_args.args[0].instruction)
        self.assertTrue(self.guide.context.manual_requested)
        self.guide.skip()
        self.hide.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
