"""FR4: deterministic risk timing, without UI, storage, or screen protection."""

from enum import Enum
from math import isfinite
from typing import Protocol

from red_handed.core.settings import MonitoringSettings, Sensitivity


class RiskStatus(Enum):
    INACTIVE = "Inactive"
    PENDING_ACTIVATION = "Pending activation"
    ACTIVE = "ACTIVE"
    PENDING_RECOVERY = "Pending recovery (risk active)"


class SensitivityPolicy(Protocol):
    """Future extension point; the team must define FR9.4 semantics first."""

    def qualifies(self, inside_zone: bool, sensitivity: Sensitivity) -> bool: ...


class PrivacyRiskEvaluator:
    """Track continuous observations using injected monotonic timestamps.

    With no SensitivityPolicy, all three selections use the geometric input
    unchanged. This is structural support for FR9.4, not its implementation.
    """

    def __init__(self, settings: MonitoringSettings,
                 sensitivity_policy: SensitivityPolicy | None = None) -> None:
        self.settings = settings
        self.sensitivity_policy = sensitivity_policy
        self.reset()

    def reset(self) -> None:
        self.status = RiskStatus.INACTIVE
        self._since: float | None = None
        self._last_time: float | None = None

    @property
    def risk_active(self) -> bool:
        return self.status in (RiskStatus.ACTIVE, RiskStatus.PENDING_RECOVERY)

    def update(self, inside_zone: bool, now: float) -> RiskStatus:
        """Advance only on a fresh valid observation; never sleep or use wall time."""
        if not isfinite(now) or (self._last_time is not None and now < self._last_time):
            raise ValueError("Risk timestamps must be finite and monotonic.")
        self._last_time = now
        if self.sensitivity_policy is not None:
            inside_zone = self.sensitivity_policy.qualifies(inside_zone, self.settings.sensitivity)

        if not self.risk_active:
            # FR4.1: separated intrusions must never accumulate activation time.
            if not inside_zone:
                self.status, self._since = RiskStatus.INACTIVE, None
            else:
                if self._since is None:
                    self._since = now
                if now - self._since >= self.settings.activation_delay:
                    self.status, self._since = RiskStatus.ACTIVE, None
                else:
                    self.status = RiskStatus.PENDING_ACTIVATION
        elif inside_zone:
            self.status, self._since = RiskStatus.ACTIVE, None
        else:
            # FR4.3: re-entry cancels recovery; zero delay clears on this update.
            if self._since is None:
                self._since = now
            if now - self._since >= self.settings.recovery_delay:
                self.status, self._since = RiskStatus.INACTIVE, None
            else:
                self.status = RiskStatus.PENDING_RECOVERY
        return self.status