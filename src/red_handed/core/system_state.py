"""Small, UI-independent representation of the Phase 1 system state."""

from dataclasses import dataclass
from enum import Enum


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

    def set_camera_available(self) -> None:
        """Record that the selected camera can be accessed."""
        self.camera_status = CameraStatus.AVAILABLE
        self.camera_error = None

    def set_camera_unavailable(self, error: str) -> None:
        """Record a camera failure and restore the safe inactive state."""
        self.camera_status = CameraStatus.UNAVAILABLE
        self.monitoring_status = MonitoringStatus.INACTIVE
        self.camera_error = error

    def start_monitoring(self) -> bool:
        """Activate monitoring only when the camera is available."""
        if self.camera_status is not CameraStatus.AVAILABLE:
            return False
        self.monitoring_status = MonitoringStatus.ACTIVE
        return True

    def stop_monitoring(self) -> None:
        """Return monitoring to the inactive state."""
        self.monitoring_status = MonitoringStatus.INACTIVE
