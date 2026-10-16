"""Connect camera capture, face detection, and shared monitoring state."""

from __future__ import annotations

from typing import Any

from red_handed.core.system_state import MonitoringStatus, SystemState
from red_handed.detection.camera import CameraManager
from red_handed.detection.person_detector import DetectionResult, PersonDetector


class MonitoringController:
    """Own the monitoring lifecycle without depending on Tkinter."""

    def __init__(
        self,
        camera: CameraManager | None = None,
        state: SystemState | None = None,
        detector: PersonDetector | None = None,
    ) -> None:
        # Injected dependencies let tests run without a webcam or native detector.
        self.camera = camera if camera is not None else CameraManager()
        self.state = state if state is not None else SystemState()
        self.detector = detector if detector is not None else PersonDetector()

        self.detection: DetectionResult | None = None
        self.detection_error: str | None = None
        self._closed = False

    def _reset_detection(self) -> None:
        """Forget the previous result when it no longer describes this session."""
        self.detection = None
        self.detection_error = None

    def _camera_failed(self, message: str) -> None:
        """Release the device and return the application to an inactive state."""
        self.camera.release()
        self.state.set_camera_unavailable(message)
        self._reset_detection()

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
        return self.state.start_monitoring()

    def read_frame(self) -> Any | None:
        """Return one camera frame and update its face-count result."""
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

        try:
            # Round 1 uses synchronous detection.
            # The development plan introduces a worker in Round 3.
            result = self.detector.detect(frame)
            if not isinstance(result, DetectionResult):
                raise TypeError("The detector returned an invalid result.")

            self.detection = result
            self.detection_error = None
        except Exception as error:
            # Failed detection means unknown, not zero people.
            # Keep the preview running and try detection again next frame.
            self.detection = None
            self.detection_error = f"Face detection unavailable: {error}"

        return frame

    def stop_monitoring(self) -> None:
        """Stop frame retrieval and release the camera."""
        self.camera.release()
        self.state.stop_monitoring()
        self._reset_detection()

        # Keep the detector available for another Start.
        # Its native resources are released only when the application closes.

    def close(self) -> None:
        """Release camera and detector resources once."""
        if self._closed:
            return

        self._closed = True
        try:
            self.stop_monitoring()
        finally:
            # Attempt detector cleanup even if stopping raises an exception.
            self.detector.close()