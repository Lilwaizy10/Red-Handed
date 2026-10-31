"""Application gating, transition recording, and persistent history checks."""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from red_handed.core.applications import (
    ActiveApplication,
    ApplicationAwarePolicy,
    ApplicationSettings,
    ProtectedApplication,
)
from red_handed.core.events import EventAction, EventRecorder, EventType
from red_handed.core.privacy_risk import RiskStatus
from red_handed.core.protection import ProtectionManager
from red_handed.core.system_state import SystemState
from red_handed.storage.event_store import EventStore
from red_handed.ui.event_history_view import EventHistoryView


class Phase5IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.state = SystemState()
        self.surface = Mock()
        self.manager = ProtectionManager(self.state, self.surface)
        self.recorder = EventRecorder()  # Synchronous, in-memory recording.
        self.manager.recorder = self.recorder
        self.addCleanup(self.recorder.close)
        self.addCleanup(self.manager.close)

    def test_application_switch_changes_automatic_protection(self):
        settings = ApplicationSettings(
            application_aware_enabled=True,
            protected_applications=(
                ProtectedApplication("Editor", r"C:\Apps\Editor.exe"),
            ),
        )

        self.manager.observe_risk(RiskStatus.ACTIVE, True, 1.0, 0.5)
        self.manager.set_application_allowed(
            ApplicationAwarePolicy.allows(
                settings,
                ActiveApplication(executable_path=r"C:\Other\Browser.exe"),
            )
        )
        self.assertFalse(self.state.protection_active)

        # Risk remains requested internally; no new risk observation is needed.
        self.manager.set_application_allowed(
            ApplicationAwarePolicy.allows(
                settings,
                ActiveApplication(executable_path=r"c:\apps\EDITOR.exe"),
            )
        )
        self.assertTrue(self.state.protection_active)

        self.manager.set_application_allowed(False)
        self.assertFalse(self.state.protection_active)

    def test_manual_protection_bypasses_gate(self):
        self.manager.set_application_allowed(False)
        self.manager.toggle_manual()

        self.assertTrue(self.state.manual_protection_requested)
        self.assertTrue(self.state.protection_active)
        self.assertFalse(self.state.automatic_protection_requested)

    def test_unknown_and_empty_list_block_enabled_policy(self):
        empty = ApplicationSettings(application_aware_enabled=True)
        unknown = ActiveApplication(error="Unavailable")

        self.assertFalse(ApplicationAwarePolicy.allows(empty, unknown))
        self.assertFalse(
            ApplicationAwarePolicy.allows(
                empty,
                ActiveApplication(executable_path=r"C:\Apps\Editor.exe"),
            )
        )
        self.assertTrue(
            ApplicationAwarePolicy.allows(ApplicationSettings(), unknown)
        )

    def test_repeated_observations_do_not_duplicate_events(self):
        for timestamp in (1.0, 1.1, 1.2):
            self.manager.observe_risk(
                RiskStatus.ACTIVE, True, timestamp, 0.5
            )

        events = self.recorder.events()
        self.assertEqual(len(events), 1)
        self.assertIs(events[0].event_type, EventType.AUTOMATIC_ACTIVATED)

        self.manager.toggle_manual()
        self.manager.stop_automatic()

        events = self.recorder.events()
        self.assertIs(events[-1].event_type, EventType.AUTOMATIC_DEACTIVATED)
        self.assertIs(events[-1].action, EventAction.STILL_PROTECTED)
        self.assertTrue(self.state.protection_active)

    def test_failed_surface_is_not_recorded_as_success(self):
        self.surface.show.side_effect = RuntimeError("Surface unavailable")
        self.manager.toggle_manual()

        self.assertFalse(self.state.protection_active)
        self.assertEqual(self.recorder.events(), [])

        self.surface.show.side_effect = None
        self.manager.select_mode(self.state.selected_protection_mode)

        self.assertTrue(self.state.protection_active)
        self.assertEqual(len(self.recorder.events()), 1)

    def test_events_and_clear_survive_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.json"
            recorder = EventRecorder(EventStore(path))
            try:
                recorder.record(
                    EventType.RISK_DETECTED,
                    EventAction.RISK_ACTIVE,
                )
                recorder.flush()
                self.assertEqual(len(EventStore(path).load()), 1)

                self.assertTrue(recorder.clear())
            finally:
                recorder.close()

            restarted = EventRecorder(EventStore(path))
            try:
                self.assertEqual(restarted.events(), [])
                self.assertIsNone(restarted.last_error)
            finally:
                restarted.close()

    def test_clear_requires_confirmation(self):
        # Exercise the callback without constructing any Tk widgets.
        view = EventHistoryView.__new__(EventHistoryView)
        view.recorder = Mock()
        view.recorder.clear.return_value = True
        view.notice = Mock()
        view.refresh = Mock()

        with patch(
            "red_handed.ui.event_history_view.messagebox.askyesno",
            return_value=False,
        ):
            view.clear_history()

        view.recorder.clear.assert_not_called()

        with patch(
            "red_handed.ui.event_history_view.messagebox.askyesno",
            return_value=True,
        ):
            view.clear_history()

        view.recorder.clear.assert_called_once()
        view.refresh.assert_called_once_with(force=True)


if __name__ == "__main__":
    unittest.main()