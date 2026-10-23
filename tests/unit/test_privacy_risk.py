"""Deterministic activation and recovery tests using explicit timestamps."""

from dataclasses import replace
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from red_handed.core.privacy_risk import PrivacyRiskEvaluator, RiskStatus
from red_handed.core.settings import MonitoringSettings


class PrivacyRiskTests(unittest.TestCase):
    def test_activation_boundary_and_continuity(self) -> None:
        settings = MonitoringSettings(
            activation_delay=3.0,
            recovery_delay=5.0,
        )
        evaluator = PrivacyRiskEvaluator(settings)

        # An intrusion starts the timer, but does not immediately activate risk.
        self.assertIs(
            evaluator.update(True, 10.0),
            RiskStatus.PENDING_ACTIVATION,
        )
        self.assertFalse(evaluator.risk_active)

        # Immediately before the boundary, risk must still be pending.
        self.assertIs(
            evaluator.update(True, 12.999),
            RiskStatus.PENDING_ACTIVATION,
        )
        self.assertFalse(evaluator.risk_active)

        # Exactly three seconds of continuous intrusion activates risk.
        self.assertIs(evaluator.update(True, 13.0), RiskStatus.ACTIVE)
        self.assertTrue(evaluator.risk_active)

        evaluator.reset()

        # Separate intrusions must not accumulate activation time.
        self.assertIs(
            evaluator.update(True, 20.0),
            RiskStatus.PENDING_ACTIVATION,
        )
        self.assertIs(evaluator.update(False, 22.0), RiskStatus.INACTIVE)
        self.assertIs(
            evaluator.update(True, 23.0),
            RiskStatus.PENDING_ACTIVATION,
        )
        self.assertIs(
            evaluator.update(True, 25.999),
            RiskStatus.PENDING_ACTIVATION,
        )
        self.assertIs(evaluator.update(True, 26.0), RiskStatus.ACTIVE)

        # Zero delay activates on the first valid inside-zone observation.
        immediate = PrivacyRiskEvaluator(
            replace(settings, activation_delay=0.0)
        )
        self.assertIs(immediate.update(True, 30.0), RiskStatus.ACTIVE)
        self.assertTrue(immediate.risk_active)

    def test_recovery_boundary_and_reentry(self) -> None:
        settings = MonitoringSettings(
            activation_delay=3.0,
            recovery_delay=5.0,
        )
        evaluator = PrivacyRiskEvaluator(settings)

        evaluator.update(True, 0.0)
        self.assertIs(evaluator.update(True, 3.0), RiskStatus.ACTIVE)

        # Recovery starts when a valid observation shows no intrusion.
        self.assertIs(
            evaluator.update(False, 4.0),
            RiskStatus.PENDING_RECOVERY,
        )
        self.assertTrue(evaluator.risk_active)

        # Pending recovery still counts as active risk.
        self.assertIs(
            evaluator.update(False, 8.999),
            RiskStatus.PENDING_RECOVERY,
        )
        self.assertTrue(evaluator.risk_active)

        # Exactly five seconds of continuous absence clears risk.
        self.assertIs(evaluator.update(False, 9.0), RiskStatus.INACTIVE)
        self.assertFalse(evaluator.risk_active)

        # Activate again, then start another recovery interval.
        evaluator.update(True, 10.0)
        self.assertIs(evaluator.update(True, 13.0), RiskStatus.ACTIVE)
        self.assertIs(
            evaluator.update(False, 14.0),
            RiskStatus.PENDING_RECOVERY,
        )
        self.assertIs(
            evaluator.update(False, 18.999),
            RiskStatus.PENDING_RECOVERY,
        )

        # Re-entry cancels recovery, even at its would-be clearing boundary.
        self.assertIs(evaluator.update(True, 19.0), RiskStatus.ACTIVE)
        self.assertTrue(evaluator.risk_active)

        # Absence must now complete a new, full recovery interval.
        self.assertIs(
            evaluator.update(False, 20.0),
            RiskStatus.PENDING_RECOVERY,
        )
        self.assertIs(
            evaluator.update(False, 24.999),
            RiskStatus.PENDING_RECOVERY,
        )
        self.assertIs(evaluator.update(False, 25.0), RiskStatus.INACTIVE)
        self.assertFalse(evaluator.risk_active)

        # Zero recovery delay clears on the first valid outside observation.
        immediate = PrivacyRiskEvaluator(
            replace(settings, activation_delay=0.0, recovery_delay=0.0)
        )
        self.assertIs(immediate.update(True, 30.0), RiskStatus.ACTIVE)
        self.assertIs(immediate.update(False, 30.1), RiskStatus.INACTIVE)
        self.assertFalse(immediate.risk_active)


if __name__ == "__main__":
    unittest.main()