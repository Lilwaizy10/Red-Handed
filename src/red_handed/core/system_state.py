"""Small, UI-independent representation of the Phase 1 system state."""

from dataclasses import dataclass
from enum import Enum
from red_handed.detection.person_detector import DetectionResult
from red_handed.detection.privacy_zone import PrivacyZone


class MonitoringStatus(Enum):
    """Whether camera-based privacy monitoring is running."""

    INACTIVE = "Inactive"
    ACTIVE = "Active"


class CameraStatus(Enum):
    """Whether the selected camera can currently be used."""

    UNAVAILABLE = "Unavailable"
    AVAILABLE = "Available"


@dataclass
class SystemState:
    """Runtime status shared by the monitoring controller and UI."""

    monitoring_status: MonitoringStatus = MonitoringStatus.INACTIVE
    camera_status: CameraStatus = CameraStatus.UNAVAILABLE
    camera_error: str | None = None
    
    # Detection belongs in shared state so all views read the same result.
    detection: DetectionResult | None = None
    detection_error: str | None = None

    # Only the saved zone affects monitoring.
    privacy_zone: PrivacyZone | None = None

    # None means unknown/unavailable; False means a valid outside-zone result.
    additional_person_in_zone: bool | None = None

    def reset_detection(self) -> None:
        """Clear transient observations without deleting the saved zone."""
        self.detection = None
        self.detection_error = None
        self.additional_person_in_zone = None

    @property
    def zone_status(self) -> str:
        """Describe zone configuration separately from a measured result."""
        if self.privacy_zone is None:
            return "Unconfigured"

        if self.monitoring_status is MonitoringStatus.INACTIVE:
            return "Inactive"

        if self.detection_error:
            return "Unknown - detection unavailable"

        if self.additional_person_in_zone is None:
            return "Waiting for detection"

        if self.additional_person_in_zone:
            return "Additional person inside zone"

        return "No additional person inside zone"

    def set_camera_available(self) -> None:
        """Record that the selected camera can be accessed."""
        self.camera_status = CameraStatus.AVAILABLE
        self.camera_error = None

    def set_camera_unavailable(self, error: str) -> None:
        """Record a camera failure and restore the safe inactive state."""
        self.camera_status = CameraStatus.UNAVAILABLE
        self.monitoring_status = MonitoringStatus.INACTIVE
        self.camera_error = error
        self.reset_detection()

    def start_monitoring(self) -> bool:
        """Activate monitoring only when the camera is available."""
        if self.camera_status is not CameraStatus.AVAILABLE:
            return False
        self.monitoring_status = MonitoringStatus.ACTIVE
        return True

    def stop_monitoring(self) -> None:
        """Return monitoring to the inactive state."""
        self.monitoring_status = MonitoringStatus.INACTIVE
        self.reset_detection()