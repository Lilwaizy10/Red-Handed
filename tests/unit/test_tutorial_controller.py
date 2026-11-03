"""Guide navigation is independent of camera, protection, and persistence."""

from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from red_handed.ui.tutorial_controller import SETUP_STEPS, TutorialController


class TutorialControllerTests(unittest.TestCase):
    def setUp(self):
        self.show = Mock()
        self.hide = Mock()
        self.guide = TutorialController(self.show, self.hide)

    def test_start_back_and_next_stay_within_steps(self):
        self.guide.back()
        self.guide.next()
        self.show.assert_not_called()
        self.assertFalse(self.guide.active)

        self.guide.start()
        self.guide.back()
        self.assertEqual(self.guide.index, 0)
        self.guide.next()
        self.show.assert_called_with(SETUP_STEPS[1], 1, len(SETUP_STEPS))
        self.guide.back()
        self.show.assert_called_with(SETUP_STEPS[0], 0, len(SETUP_STEPS))

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

    def test_last_step_closes_instead_of_advancing_out_of_bounds(self):
        self.guide.start()
        for _ in SETUP_STEPS:
            self.guide.next()
        self.assertFalse(self.guide.active)
        self.hide.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
