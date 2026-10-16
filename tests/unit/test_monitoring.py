"""Controller tests using fake dependencies instead of a physical webcam."""

from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

# Allow tests to import the application directly from the source directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from red_handed.core.monitoring import MonitoringController
from red_handed.core.system_state import CameraStatus, MonitoringStatus
from red_handed.detection.camera import CameraManager
from red_handed.detection.person_detector import DetectionResult, PersonDetector


class MonitoringControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.camera = Mock(spec=CameraManager)
        self.camera.last_error = None
        self.camera.check_availability.return_value = True
        self.camera.open.return_value = True

        # The controller passes frames through without interpreting their pixels.
        self.frame = object()
        self.camera.read_frame.return_value = self.frame

        self.detector = Mock(spec=PersonDetector)
        self.detector.detect.return_value = DetectionResult(person_count=2)

        self.controller = MonitoringController(
            camera=self.camera,
            detector=self.detector,
        )
        self.addCleanup(self.controller.close)

    def test_unavailable_camera_can_be_retried(self) -> None:
        self.camera.check_availability.side_effect = [False, True]
        self.camera.last_error = "Camera disconnected."

        self.assertFalse(self.controller.refresh_camera_availability())
        self.assertIs(
            self.controller.state.camera_status,
            CameraStatus.UNAVAILABLE,
        )
        self.assertEqual(
            self.controller.state.camera_error,
            "Camera disconnected.",
        )

        self.assertTrue(self.controller.refresh_camera_availability())
        self.assertIs(
            self.controller.state.camera_status,
            CameraStatus.AVAILABLE,
        )
        self.assertIsNone(self.controller.state.camera_error)

    def test_failed_start_keeps_monitoring_inactive(self) -> None:
        self.camera.open.return_value = False
        self.camera.last_error = "Camera permission denied."

        self.assertFalse(self.controller.start_monitoring())
        self.assertIs(
            self.controller.state.monitoring_status,
            MonitoringStatus.INACTIVE,
        )
        self.assertEqual(
            self.controller.state.camera_error,
            "Camera permission denied.",
        )
        self.camera.release.assert_called_once()
        self.detector.detect.assert_not_called()

    def test_repeated_start_opens_camera_once(self) -> None:
        self.assertTrue(self.controller.start_monitoring())
        self.assertTrue(self.controller.start_monitoring())

        self.camera.open.assert_called_once()
        self.assertIs(
            self.controller.state.monitoring_status,
            MonitoringStatus.ACTIVE,
        )

    def test_active_camera_is_not_probed_again(self) -> None:
        self.controller.start_monitoring()

        self.assertTrue(self.controller.refresh_camera_availability())
        self.camera.check_availability.assert_not_called()

    def test_frame_updates_detected_count(self) -> None:
        self.controller.start_monitoring()

        frame = self.controller.read_frame()

        self.assertIs(frame, self.frame)
        self.detector.detect.assert_called_once_with(self.frame)
        self.assertEqual(self.controller.detection.person_count, 2)
        self.assertIsNone(self.controller.detection_error)

    def test_successful_zero_is_not_unknown(self) -> None:
        self.detector.detect.return_value = DetectionResult(person_count=0)
        self.controller.start_monitoring()

        self.controller.read_frame()

        self.assertIsNotNone(self.controller.detection)
        self.assertEqual(self.controller.detection.person_count, 0)
        self.assertIsNone(self.controller.detection_error)

    def test_detection_failure_keeps_preview_and_can_recover(self) -> None:
        self.detector.detect.side_effect = [
            RuntimeError("Model unavailable."),
            DetectionResult(person_count=1),
        ]
        self.controller.start_monitoring()

        # The first frame still reaches the preview despite failed detection.
        self.assertIs(self.controller.read_frame(), self.frame)
        self.assertIsNone(self.controller.detection)
        self.assertIn("Model unavailable", self.controller.detection_error)
        self.assertIs(
            self.controller.state.monitoring_status,
            MonitoringStatus.ACTIVE,
        )

        # A later successful result replaces the error.
        self.controller.read_frame()
        self.assertEqual(self.controller.detection.person_count, 1)
        self.assertIsNone(self.controller.detection_error)

    def test_camera_loss_clears_previous_result_and_releases_device(self) -> None:
        self.controller.start_monitoring()
        self.controller.read_frame()
        self.camera.read_frame.return_value = None
        self.camera.last_error = "Camera disconnected."

        self.assertIsNone(self.controller.read_frame())
        self.assertIsNone(self.controller.detection)
        self.assertIs(
            self.controller.state.monitoring_status,
            MonitoringStatus.INACTIVE,
        )
        self.assertIs(
            self.controller.state.camera_status,
            CameraStatus.UNAVAILABLE,
        )
        self.camera.release.assert_called_once()

    def test_stop_prevents_reads_and_allows_restart(self) -> None:
        self.controller.start_monitoring()
        self.controller.read_frame()

        self.controller.stop_monitoring()
        self.camera.read_frame.reset_mock()
        self.detector.detect.reset_mock()

        self.assertIsNone(self.controller.read_frame())
        self.camera.read_frame.assert_not_called()
        self.detector.detect.assert_not_called()
        self.assertIsNone(self.controller.detection)
        self.camera.release.assert_called_once()
        self.detector.close.assert_not_called()

        self.assertTrue(self.controller.start_monitoring())
        self.assertIs(self.controller.read_frame(), self.frame)

    def test_close_releases_resources_once_and_prevents_restart(self) -> None:
        self.controller.start_monitoring()

        self.controller.close()
        self.controller.close()

        self.camera.release.assert_called_once()
        self.detector.close.assert_called_once()
        self.assertFalse(self.controller.start_monitoring())
        self.assertIsNone(self.controller.read_frame())


if __name__ == "__main__":
    unittest.main()