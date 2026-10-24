"""Zone integration tests without a physical camera or native face detector."""

from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from monitoring_test_support import (
    FakeClock,
    FakeFrame,
    ImmediateExecutor,
    read_detection,
)

from red_handed.core.monitoring import MonitoringController
from red_handed.core.settings import MonitoringSettings
from red_handed.core.system_state import MonitoringStatus
from red_handed.detection.camera import CameraManager
from red_handed.detection.person_detector import DetectionResult, PersonDetector
from red_handed.detection.privacy_zone import PrivacyZone


class ZoneMonitoringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.camera = Mock(spec=CameraManager)
        self.camera.open.return_value = True
        self.camera.last_error = None

        # Only frame dimensions are needed because detection is mocked.
        self.frame = FakeFrame()
        self.clock = FakeClock()
        self.camera.read_frame.return_value = self.frame

        self.detector = Mock(spec=PersonDetector)
        self.zone = PrivacyZone(0.6, 0.0, 0.4, 1.0)
        self.settings = MonitoringSettings(privacy_zone=self.zone)

        self.controller = MonitoringController(
            camera=self.camera,
            detector=self.detector,
            settings=self.settings,
            clock=self.clock,
            executor=ImmediateExecutor(),
        )
        self.addCleanup(self.controller.close)
        self.controller.start_monitoring()

    def observe(self, boxes) -> None:
        """Supply one deterministic detector result."""
        self.detector.detect.return_value = DetectionResult(
            person_count=len(boxes),
            bounding_boxes=boxes,
        )
        read_detection(self.controller, self.clock)

    def test_no_zone_is_unconfigured(self) -> None:
        self.controller.apply_settings(MonitoringSettings())
        self.observe(((0, 0, 100, 100), (140, 20, 20, 20)))

        self.assertIsNone(self.controller.state.additional_person_in_zone)
        self.assertEqual(self.controller.state.zone_status, "Unconfigured")
        self.assertEqual(self.controller.detection.person_count, 2)

    def test_inside_outside_and_boundary(self) -> None:
        primary = (0, 0, 100, 100)

        for additional, expected in [
            ((140, 20, 20, 20), True),
            ((100, 20, 10, 10), False),
            # Centre x=120, exactly the zone's left boundary: included.
            ((110, 20, 20, 20), True),
        ]:
            with self.subTest(additional=additional):
                self.observe((primary, additional))
                self.assertIs(
                    self.controller.state.additional_person_in_zone,
                    expected,
                )

    def test_largest_face_is_excluded_even_when_inside_zone(self) -> None:
        # The largest face is inside; the additional smaller face is outside.
        self.observe(((120, 0, 80, 100), (10, 10, 20, 20)))

        self.assertIs(self.controller.state.additional_person_in_zone, False)

    def test_zero_or_one_face_has_no_additional_person(self) -> None:
        for boxes in [(), ((140, 20, 20, 20),)]:
            with self.subTest(boxes=boxes):
                self.observe(boxes)
                self.assertIs(
                    self.controller.state.additional_person_in_zone,
                    False,
                )

    def test_settings_change_clears_old_observation(self) -> None:
        self.observe(((0, 0, 100, 100), (140, 20, 20, 20)))
        replacement = replace(
            self.settings,
            privacy_zone=PrivacyZone(0.0, 0.0, 0.4, 1.0),
        )

        self.controller.apply_settings(replacement)

        self.assertIsNone(self.controller.detection)
        self.assertIsNone(self.controller.state.additional_person_in_zone)
        self.assertEqual(self.controller.state.privacy_zone, replacement.privacy_zone)
        self.assertIs(
            self.controller.state.monitoring_status,
            MonitoringStatus.ACTIVE,
        )
        self.assertEqual(
            self.controller.state.zone_status,
            "Waiting for detection",
        )

    def test_detector_failure_clears_membership_and_can_recover(self) -> None:
        boxes = ((0, 0, 100, 100), (140, 20, 20, 20))
        self.observe(boxes)
        self.detector.detect.side_effect = RuntimeError("Detector failed.")

        self.assertIs(read_detection(self.controller, self.clock), self.frame)
        self.assertIsNone(self.controller.state.additional_person_in_zone)
        self.assertEqual(
            self.controller.state.zone_status,
            "Unknown - detection unavailable",
        )

        self.detector.detect.side_effect = None
        self.observe(boxes)
        self.assertIs(self.controller.state.additional_person_in_zone, True)

    def test_stop_clears_membership_but_keeps_saved_zone(self) -> None:
        self.observe(((0, 0, 100, 100), (140, 20, 20, 20)))

        self.controller.stop_monitoring()

        self.assertIsNone(self.controller.state.additional_person_in_zone)
        self.assertEqual(self.controller.state.privacy_zone, self.zone)
        self.assertEqual(self.controller.state.zone_status, "Inactive")

    def test_camera_loss_clears_membership(self) -> None:
        self.observe(((0, 0, 100, 100), (140, 20, 20, 20)))
        self.camera.read_frame.return_value = None

        self.assertIsNone(self.controller.read_frame())
        self.assertIsNone(self.controller.state.additional_person_in_zone)
        self.assertIs(
            self.controller.state.monitoring_status,
            MonitoringStatus.INACTIVE,
        )

    def test_inconsistent_boxes_are_unknown(self) -> None:
        self.detector.detect.return_value = DetectionResult(
            person_count=2,
            bounding_boxes=((0, 0, 100, 100),),
        )

        read_detection(self.controller, self.clock)

        self.assertEqual(self.controller.detection.person_count, 2)
        self.assertIsNone(self.controller.state.additional_person_in_zone)
        self.assertIsNone(self.controller.state.risk_status)
        self.assertFalse(self.controller.state.privacy_risk_active)


if __name__ == "__main__":
    unittest.main()