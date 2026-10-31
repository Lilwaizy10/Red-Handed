"""Connect camera capture, bounded face detection, and the privacy-risk pipeline."""

from __future__ import annotations

from typing import Any
from collections.abc import Callable
from concurrent.futures import Executor, Future, ThreadPoolExecutor
from time import monotonic

from red_handed.core.system_state import MonitoringStatus, SystemState
from red_handed.detection.camera import CameraManager
from red_handed.detection.person_detector import DetectionResult, PersonDetector
from red_handed.core.settings import MonitoringSettings
from red_handed.detection.privacy_zone import split_primary_face
from red_handed.core.privacy_risk import PrivacyRiskEvaluator
from red_handed.core.events import EventType, EventAction
from red_handed.core.system_state import CameraStatus


class MonitoringController:
    """Own the monitoring lifecycle without depending on Tkinter."""

    # Evidence freshness, not sensitivity: do not bridge stalled detection periods.
    MAX_OBSERVATION_GAP = 1.0

    def __init__(
        self,
        camera: CameraManager | None = None,
        state: SystemState | None = None,
        detector: PersonDetector | None = None,
        settings: MonitoringSettings | None = None,
        *,
        detection_interval: float = 0.1,
        clock: Callable[[], float] = monotonic,
        executor: Executor | None = None,
    ) -> None:
        # Injected dependencies let tests run without a webcam or native detector.
        self.camera = camera if camera is not None else CameraManager()
        self.state = state if state is not None else SystemState()
        self.detector = detector if detector is not None else PersonDetector()

        if detection_interval <= 0:
            raise ValueError("Detection interval must be positive.")
        self._detection_interval = detection_interval
        self._clock = clock
        self._executor = executor
        self._pending: Future[DetectionResult] | None = None
        self._session = 0
        self._pending_session = 0
        self._next_detection_at = 0.0
        self._pending_frame_size: tuple[int, int] | None = None
        self._pending_captured_at = 0.0
        self._last_risk_observation: float | None = None
        self.recorder = None
        self._recorded_risk = False
        # The UI owns the surface and manager; the controller publishes risk.
        self.protection = None
        self._closed = False
        initial = settings if settings is not None else MonitoringSettings()
        self.risk_evaluator = PrivacyRiskEvaluator(initial)
        self.apply_settings(initial)

    @property
    def detection(self) -> DetectionResult | None:
        """Keep the Phase 1 read interface while sharing state with the UI."""
        return self.state.detection

    @property
    def detection_error(self) -> str | None:
        """Expose the shared detection error through the existing interface."""
        return self.state.detection_error

    def _reset_detection(self) -> None:
        """Discard observations from before Stop, failure, or a settings change."""
        self.state.reset_detection()

    def apply_settings(self, settings: MonitoringSettings) -> None:
        """Apply validated settings and wait for a fresh detection result."""
        if self._closed:
            raise RuntimeError("Cannot apply settings to a closed controller.")

        if not isinstance(settings, MonitoringSettings):
            raise ValueError("Invalid monitoring settings.")

        self.settings = settings
        self.state.privacy_zone = settings.privacy_zone
        self.risk_evaluator.settings = settings
        self._reset_detection()
        self._cancel_detection()
        self._next_detection_at = self._clock()

    def attach_protection(self, manager) -> None:
        """Connect or disconnect protection without creating another frame loop."""
        self.protection = manager
        self._sync_protection()

    def _sync_protection(self) -> None:
        """Publish the current risk observation to the protection manager."""
        active = self.state.privacy_risk_active

        # Pending recovery remains active, so it must not create another event.
        if active and not self._recorded_risk and self.recorder is not None:
            self.recorder.record(
                EventType.RISK_DETECTED,
                EventAction.RISK_ACTIVE,
            )

        self._recorded_risk = active
        if self.protection is None:
            return

        self.protection.observe_risk(
            self.state.risk_status,
            self.state.additional_person_in_zone,
            self._last_risk_observation,
            self.settings.recovery_delay,
        )

    def _reset_risk(self) -> None:
        """Discard timing built from evidence that is no longer valid."""
        self.risk_evaluator.reset()
        self.state.reset_risk()
        self._last_risk_observation = None
        self._sync_protection()

    def _update_risk(self, result: DetectionResult) -> None:
        """FR3.4 / FR4: evaluate boxes against the saved zone on fresh results only."""
        zone = self.settings.privacy_zone
        if zone is None or self._pending_frame_size is None:
            self._reset_risk()
            return
        sampled_at = self._pending_captured_at
        # A count without matching boxes, or a late result, cannot support a decision.
        if (self._clock() - sampled_at > self.MAX_OBSERVATION_GAP
                or len(result.bounding_boxes) != result.person_count):
            self._reset_risk()
            return
        if (self._last_risk_observation is not None
                and sampled_at - self._last_risk_observation > self.MAX_OBSERVATION_GAP):
            self._reset_risk()
        # Only the other faces are considered additional people.
        _, additional = split_primary_face(result.bounding_boxes)
        width, height = self._pending_frame_size
        inside = any(zone.contains_face(box, width, height)
                     for box in additional)
        self.state.additional_person_in_zone = inside
        self.state.risk_status = self.risk_evaluator.update(inside, sampled_at)
        self._last_risk_observation = sampled_at
        self._sync_protection()

    def _camera_failed(self, message: str) -> None:
        """Stop monitoring and record an available-to-unavailable transition."""
        was_available = (
            self.state.camera_status is CameraStatus.AVAILABLE
        )

        self.camera.release()
        self.state.set_camera_unavailable(message)
        self._reset_detection()
        self._cancel_detection()

        if was_available and self.recorder is not None:
            self.recorder.record(
                EventType.CAMERA_UNAVAILABLE,
                EventAction.CAMERA_UNAVAILABLE,
            )

    def refresh_camera_availability(self) -> bool:
        """Check whether the camera is usable, including after a failed attempt."""
        if self._closed:
            return False

        # Do not probe a second camera connection while monitoring owns it.
        if self.state.monitoring_status is MonitoringStatus.ACTIVE:
            return True

        if self.camera.check_availability():
            self.state.set_camera_available()
            return True

        self._camera_failed(
            self.camera.last_error or "No usable camera is available."
        )
        return False

    def start_monitoring(self) -> bool:
        """Open the camera before marking monitoring as active."""
        if self._closed:
            return False

        # Repeated Start requests must not open another camera connection.
        if self.state.monitoring_status is MonitoringStatus.ACTIVE:
            return True

        if not self.camera.open():
            self._camera_failed(
                self.camera.last_error or "The camera could not be opened."
            )
            return False

        self.state.set_camera_available()
        self._reset_detection()
        self._next_detection_at = self._clock()
        return self.state.start_monitoring()

    def read_frame(self) -> Any | None:
        """Read a frame and schedule bounded face detection on it."""
        if self._closed:
            return None

        if self.state.monitoring_status is not MonitoringStatus.ACTIVE:
            return None

        frame = self.camera.read_frame()
        if frame is None:
            self._camera_failed(
                self.camera.last_error or "Camera access was lost."
            )
            return None

        # A detection failure should not prevent the camera preview.
        self._update_detection(frame)
        return frame

    def _update_detection(self, frame: Any) -> None:
        """Collect a finished result, then submit at most one new frame."""
        if (self._last_risk_observation is not None
                and self._clock() - self._last_risk_observation > self.MAX_OBSERVATION_GAP):
            self._reset_risk()
        if self._pending is not None:
            if not self._pending.done():
                return  # At most one frame in flight; never build a backlog.
            pending, self._pending = self._pending, None
            # A result from before Stop, camera loss, or a settings change is stale.
            if self._pending_session == self._session:
                try:
                    result = pending.result()
                    if not isinstance(result, DetectionResult):
                        raise TypeError(
                            "The detector returned an invalid result.")
                    self.state.detection = result
                    self.state.detection_error = None
                    self._update_risk(result)
                except Exception as error:
                    # Never retain a reassuring old zone result after detection fails.
                    self._reset_risk()
                    self._reset_detection()
                    self.state.detection_error = (
                        f"Face detection unavailable: {error}"
                    )

        # Throttle submissions to the configured detection interval.
        now = self._clock()
        if now < self._next_detection_at:
            return
        self._next_detection_at = now + self._detection_interval
        try:
            if self._executor is None:
                self._executor = ThreadPoolExecutor(
                    max_workers=1, thread_name_prefix="red-handed-detection"
                )
            # One owned in-memory copy. The UI and worker never mutate a shared frame.
            self._pending_frame_size = (
                (frame.shape[1], frame.shape[0])
                if self.settings.privacy_zone is not None else None
            )
            self._pending_captured_at = now
            self._pending = self._executor.submit(
                self.detector.detect, frame.copy())
            self._pending_session = self._session
        except Exception:
            self._reset_risk()
            self._reset_detection()
            self.state.detection_error = "Detection unavailable. Stop and restart monitoring."

    def _cancel_detection(self) -> None:
        """Stop scheduling work and ignore any result from the previous session.

        A running detector call cannot be interrupted. It may finish its current
        in-memory frame, but must never update stopped/restarted session state.
        Keep its future until finished to prevent concurrent detector calls.
        """
        self._session += 1
        self._reset_risk()
        if self._pending is not None and self._pending.cancel():
            self._pending = None

    def stop_monitoring(self) -> None:
        """Stop frame retrieval and release the camera."""
        self.camera.release()
        self.state.stop_monitoring()
        self._reset_detection()
        self._cancel_detection()
        # Explicit Stop clears automatic protection only.
        # A separate manual request must remain active.
        if self.protection is not None:
            self.protection.stop_automatic()

        # Keep the detector available for another Start.

    def close(self) -> None:
        """Release camera and detector resources once."""
        if self._closed:
            return

        self._closed = True
        try:
            self.stop_monitoring()
        finally:
            try:
                if self._executor is not None:
                    # No queued frames; allow the one bounded detector call to finish.
                    self._executor.shutdown(wait=True, cancel_futures=True)
                    self._executor = None
                self._pending = None
            finally:
                # Attempt detector cleanup even if stopping raises an exception.
                self.detector.close()
