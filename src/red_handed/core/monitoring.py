"""Connect camera capture, face detection, and shared monitoring state."""

from __future__ import annotations

from typing import Any

from red_handed.core.system_state import MonitoringStatus, SystemState
from red_handed.detection.camera import CameraManager
from red_handed.detection.person_detector import DetectionResult, PersonDetector
from red_handed.core.settings import MonitoringSettings
from red_handed.detection.privacy_zone import split_primary_face


class MonitoringController:
    """Own the monitoring lifecycle without depending on Tkinter."""

    def __init__(
        self,
        camera: CameraManager | None = None,
        state: SystemState | None = None,
        detector: PersonDetector | None = None,
        settings: MonitoringSettings | None = None,
    ) -> None:
        # Injected dependencies let tests run without a webcam or native detector.
        self.camera = camera if camera is not None else CameraManager()
        self.state = state if state is not None else SystemState()
        self.detector = detector if detector is not None else PersonDetector()

        self._closed = False
        self.apply_settings(
            settings if settings is not None else MonitoringSettings()
        )

    @property
    def detection(self) -> DetectionResult | None:
        """Keep the Round 1 read interface while sharing state with the UI."""
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
        self._reset_detection()

    def _zone_membership(
        self,
        frame: Any,
        result: DetectionResult,
    ) -> bool | None:
        """Check additional face centres against the saved normalized zone."""
        zone = self.settings.privacy_zone
        if zone is None:
            return None

        # A count without matching boxes cannot support a zone decision.
        if len(result.bounding_boxes) != result.person_count:
            raise ValueError("Face count and bounding boxes do not match.")

        # Detector boxes use the original camera frame's pixel coordinates.
        frame_height, frame_width = frame.shape[:2]
        if frame_width <= 0 or frame_height <= 0:
            raise ValueError("Frame dimensions must be positive.")

        # Only the other faces are considered additional people.
        _, additional_faces = split_primary_face(result.bounding_boxes)

        return any(
            zone.contains_face(box, frame_width, frame_height)
            for box in additional_faces
        )

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
        """Read a frame, update face detection, and evaluate the saved zone."""
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
            # Detection remains synchronous until the later async work.
            result = self.detector.detect(frame)
            if not isinstance(result, DetectionResult):
                raise TypeError("The detector returned an invalid result.")

            # Calculate membership before publishing the complete observation.
            inside = self._zone_membership(frame, result)

            self.state.detection = result
            self.state.detection_error = None
            self.state.additional_person_in_zone = inside
        except Exception as error:
            # Never retain a reassuring old zone result after detection fails.
            self._reset_detection()
            self.state.detection_error = (
                f"Face detection unavailable: {error}"
            )

        # A detection failure should not prevent the camera preview.
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