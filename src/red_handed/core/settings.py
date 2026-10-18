from dataclasses import dataclass
from enum import Enum
from math import isfinite

from red_handed.detection.privacy_zone import PrivacyZone


class Sensitivity(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


@dataclass(frozen=True)
class MonitoringSettings:
    """FR9: no privacy zone is chosen for the user."""

    privacy_zone: PrivacyZone | None = None
    sensitivity: Sensitivity = Sensitivity.MEDIUM
    activation_delay: float = 3.0
    recovery_delay: float = 5.0

    def __post_init__(self) -> None:
        if self.privacy_zone is not None and not isinstance(self.privacy_zone, PrivacyZone):
            raise ValueError("Invalid privacy zone.")
        if not isinstance(self.sensitivity, Sensitivity):
            raise ValueError("Sensitivity must be Low, Medium, or High.")
        for label, delay in [("Activation", self.activation_delay), ("Recovery", self.recovery_delay)]:
            if (isinstance(delay, bool) or not isinstance(delay, (int, float))
                    or not isfinite(delay) or not 0 <= delay <= 10):
                raise ValueError(f"{label} delay must be a finite number from 0 to 10 seconds.")