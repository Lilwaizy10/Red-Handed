from dataclasses import dataclass
from enum import Enum
from math import isfinite

from red_handed.detection.privacy_zone import PrivacyZone
from red_handed.system.hotkey_manager import parse_hotkey


class ProtectionMode(str, Enum):
    PRIVACY_OVERLAY = "Privacy Overlay"
    SCREEN_BLACKOUT = "Screen Blackout"
    DECOY_WEBSITE = "Decoy Website"


@dataclass(frozen=True)
class ProtectionSettings:
    """FR7 / FR10: defaults from the mockup; separate from risk configuration."""

    mode: ProtectionMode = ProtectionMode.PRIVACY_OVERLAY
    hotkey: str = "Ctrl+Alt+P"

    def __post_init__(self):
        if not isinstance(self.mode, ProtectionMode):
            raise ValueError("Select Privacy Overlay, Screen Blackout, or Open Preferred Website option.")
        # Reject non-text first: a hand-edited settings file could hold a number
        # or null here, and parse_hotkey might raise AttributeError (which the
        # settings store does not catch) instead of ValueError.
        if not isinstance(self.hotkey, str):
            raise ValueError("Hotkey must be text.")
        # Store the normalised form so equivalent spellings compare equal.
        object.__setattr__(self, 'hotkey', parse_hotkey(self.hotkey).text)
        


class Sensitivity(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


@dataclass(frozen=True)
class MonitoringSettings:
    """FR9: defaults follow the mockup; no privacy zone is chosen for the user."""

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