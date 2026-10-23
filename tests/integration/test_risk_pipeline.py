"""Controller-to-risk integration with controlled futures and timestamps."""

from concurrent.futures import Executor, Future
from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from monitoring_test_support import FakeClock, FakeFrame

from red_handed.core.monitoring import MonitoringController
from red_handed.core.privacy_risk import RiskStatus
from red_handed.core.settings import MonitoringSettings
from red_handed.core.system_state import MonitoringStatus
from red_handed.detection.camera import CameraManager
from red_handed.detection.person_detector import DetectionResult, PersonDetector
from red_handed.detection.privacy_zone import PrivacyZone


class ControlledExecutor(Executor):
    """Simulate one running worker whose completion is controlled by the test."""

    def __init__(self) -> None:
        self.pending = None
        self.frames = []

    def submit(self, function, /, frame):
        if self.pending is not None:
            raise AssertionError("A second detection was submitted while busy.")

        future = Future()

        # Simulate an already-running native call: Stop cannot cancel it.
        future.set_running_or_notify_cancel()
        self.pending = future
        self.frames.append(frame)
        return future

    def finish(self, result=None, *, error=None) -> None:
        if self.pending is None:
            raise AssertionError("There is no pending detection to complete.")

        future = self.pending
        self.pending = None

        if error is not None:
            future.set_exception(error)
        else:
            future.set_result(result)

    def shutdown(self, wait=True, *, cancel_futures=False):
        # This executor has no real threads to join.
        pass


class RiskPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.executor = ControlledExecutor()
        self.frame = FakeFrame()

        self.camera = Mock(spec=CameraManager)
        self.camera.open.return_value = True
        self.camera.read_frame.return_value = self.frame
        self.camera.last_error = None

        self.settings = MonitoringSettings(
            privacy_zone=PrivacyZone(0.6, 0.0, 0.4, 1.0),
            activation_delay=0.5,
            recovery_delay=0.5,
        )
        self.controller = MonitoringController(
            camera=self.camera,
            detector=Mock(spec=PersonDetector),
            settings=self.settings,
            clock=self.clock,
            executor=self.executor,
        )
        self.addCleanup(self.controller.close)
        self.controller.start_monitoring()

    @staticmethod
    def result(inside: bool) -> DetectionResult:
        # The larger face is primary; the smaller face moves across the zone.
        primary = (0, 0, 100, 100)
        additional = (
            (140, 20, 20, 20) if inside else (100, 20, 10, 10)
        )
        return DetectionResult(
            person_count=2,
            bounding_boxes=(primary, additional),
        )

    def sample(self, timestamp: float, inside: bool) -> None:
        """Submit a frame, finish its worker, then collect the result."""
        self.clock.now = timestamp
        self.controller.read_frame()
        self.executor.finish(self.result(inside))
        self.controller.read_frame()

    def test_activation_recovery_and_reentry_through_controller(self) -> None:
        observations = [
            (0.0, True, RiskStatus.PENDING_ACTIVATION),
            (0.25, True, RiskStatus.PENDING_ACTIVATION),
            (0.5, True, RiskStatus.ACTIVE),
            (0.75, False, RiskStatus.PENDING_RECOVERY),
            (1.0, True, RiskStatus.ACTIVE),  # Re-entry cancels recovery.
            (1.25, False, RiskStatus.PENDING_RECOVERY),
            (1.5, False, RiskStatus.PENDING_RECOVERY),
            (1.75, False, RiskStatus.INACTIVE),
        ]

        for timestamp, inside, expected in observations:
            with self.subTest(timestamp=timestamp):
                self.sample(timestamp, inside)
                self.assertIs(self.controller.state.risk_status, expected)
                self.assertIs(
                    self.controller.state.additional_person_in_zone,
                    inside,
                )
                self.assertEqual(
                    self.controller.state.privacy_risk_active,
                    expected in (
                        RiskStatus.ACTIVE,
                        RiskStatus.PENDING_RECOVERY,
                    ),
                )

    def test_bounded_worker_and_old_session_result_is_ignored(self) -> None:
        self.controller.read_frame()

        # Further preview frames must not create a backlog of detector jobs.
        self.clock.now = 0.25
        for _ in range(5):
            self.controller.read_frame()

        self.assertEqual(len(self.executor.frames), 1)
        self.assertIsNot(self.executor.frames[0], self.frame)

        self.controller.stop_monitoring()
        self.controller.start_monitoring()

        # The old worker finishes after restart. Its result must be discarded.
        self.executor.finish(self.result(True))
        self.controller.read_frame()

        self.assertIsNone(self.controller.detection)
        self.assertIsNone(self.controller.state.risk_status)
        self.assertEqual(len(self.executor.frames), 2)

        # The newly submitted session's result is accepted.
        self.executor.finish(self.result(False))
        self.controller.read_frame()

        self.assertIs(
            self.controller.state.risk_status,
            RiskStatus.INACTIVE,
        )

    def test_late_result_cannot_extend_existing_risk_timing(self) -> None:
        self.sample(0.0, True)
        self.sample(0.5, True)
        self.assertTrue(self.controller.state.privacy_risk_active)

        self.clock.now = 0.75
        self.controller.read_frame()

        # This result is older than the controller's one-second freshness limit.
        self.clock.now = 2.0
        self.executor.finish(self.result(True))
        self.controller.read_frame()

        self.assertIsNone(self.controller.state.risk_status)
        self.assertIsNone(self.controller.state.additional_person_in_zone)
        self.assertFalse(self.controller.state.privacy_risk_active)

    def test_detector_failure_is_unknown_then_valid_absence_is_inactive(self) -> None:
        self.sample(0.0, True)
        self.sample(0.5, True)

        self.clock.now = 0.75
        self.controller.read_frame()
        self.executor.finish(error=RuntimeError("Detector failed."))
        self.controller.read_frame()

        # Unknown evidence must not be represented as a measured safe state.
        self.assertIsNone(self.controller.state.risk_status)
        self.assertIsNone(self.controller.state.additional_person_in_zone)
        self.assertIn("Detector failed", self.controller.detection_error)

        self.sample(1.0, False)

        self.assertIs(
            self.controller.state.risk_status,
            RiskStatus.INACTIVE,
        )
        self.assertIs(
            self.controller.state.additional_person_in_zone,
            False,
        )
        self.assertIsNone(self.controller.detection_error)

    def test_camera_loss_resets_timing_before_restart(self) -> None:
        self.sample(0.0, True)
        self.sample(0.5, True)

        self.camera.read_frame.return_value = None
        self.camera.last_error = "Camera disconnected."
        self.controller.read_frame()

        self.assertIs(
            self.controller.state.monitoring_status,
            MonitoringStatus.INACTIVE,
        )
        self.assertIsNone(self.controller.state.risk_status)

        self.camera.read_frame.return_value = self.frame
        self.controller.start_monitoring()
        self.sample(1.0, True)

        # Restart must begin a new activation interval.
        self.assertIs(
            self.controller.state.risk_status,
            RiskStatus.PENDING_ACTIVATION,
        )

    def test_settings_change_rejects_pending_result_and_restarts_timer(self) -> None:
        self.sample(0.0, True)
        self.sample(0.5, True)

        self.clock.now = 0.75
        self.controller.read_frame()

        updated = replace(self.settings, activation_delay=1.0)
        self.controller.apply_settings(updated)

        self.assertIsNone(self.controller.state.risk_status)

        # The in-flight result belongs to the previous settings session.
        self.executor.finish(self.result(True))
        self.controller.read_frame()
        self.assertIsNone(self.controller.state.risk_status)

        # Complete the new session's frame captured at 0.75.
        self.executor.finish(self.result(True))
        self.controller.read_frame()
        self.assertIs(
            self.controller.state.risk_status,
            RiskStatus.PENDING_ACTIVATION,
        )

        self.sample(1.25, True)
        self.assertIs(
            self.controller.state.risk_status,
            RiskStatus.PENDING_ACTIVATION,
        )

        self.sample(1.75, True)
        self.assertIs(
            self.controller.state.risk_status,
            RiskStatus.ACTIVE,
        )


if __name__ == "__main__":
    unittest.main()