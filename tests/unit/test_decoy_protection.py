"""Decoy lifecycle checks without Chrome, camera access or real hotkeys."""

from pathlib import Path
from threading import Event
from time import monotonic, sleep
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from red_handed.core.protection import ProtectionManager
from red_handed.core.settings import ProtectionMode
from red_handed.core.system_state import SystemState
from red_handed.core.applications import ActiveApplication, ApplicationSettings, ProtectedApplication
from red_handed.ui.main_window import MainWindow
from red_handed.ui.static_web_opener import StaticWebOpener


class FakeWebOpener:
    def __init__(self):
        self.ready = False
        self.starting = False
        self.last_error = None
        self.browser_pid = 123
        self.requests = 0

    def open(self):
        self.requests += 1

    def close(self):
        self.ready = False
        self.starting = False

    def shutdown(self):
        self.close()


class DecoyProtectionTests(unittest.TestCase):
    def setUp(self):
        self.state = SystemState()
        self.surface = Mock(window=None)
        self.web = FakeWebOpener()
        self.manager = ProtectionManager(self.state, self.surface,
            ProtectionMode.DECOY_WEBSITE, web_opener=self.web)
        self.addCleanup(self.manager.close)

    def test_pending_decoy_uses_overlay_then_switches_when_ready(self):
        self.manager.toggle_manual()
        self.assertTrue(self.state.protection_active)
        self.assertIs(self.manager.active_mode, ProtectionMode.PRIVACY_OVERLAY)
        self.web.ready = True
        self.manager.set_application_allowed(True)
        self.assertIs(self.manager.active_mode, ProtectionMode.DECOY_WEBSITE)
        self.surface.hide.assert_called_once()

    def test_external_close_restores_overlay_without_new_risk(self):
        self.web.ready = True
        self.manager.set_automatic(True)
        self.web.ready = False
        self.web.last_error = "Window closed"
        self.manager.set_application_allowed(True)
        self.assertIs(self.manager.active_mode, ProtectionMode.PRIVACY_OVERLAY)
        self.assertIn("Window closed", self.manager.notice)
        self.assertTrue(self.state.protection_active)
        self.web.ready = True
        self.manager.set_application_allowed(True)
        self.assertIs(self.manager.active_mode, ProtectionMode.DECOY_WEBSITE)

    def test_failed_switch_cannot_be_cached_as_success(self):
        self.web.ready = True
        self.manager.toggle_manual()
        self.surface.show.side_effect = RuntimeError("surface failed")
        self.manager.select_mode(ProtectionMode.SCREEN_BLACKOUT)
        self.assertFalse(self.state.protection_active)
        self.assertIsNone(self.manager._presentation)
        self.surface.show.side_effect = None
        before = self.web.requests
        self.manager.select_mode(ProtectionMode.DECOY_WEBSITE)
        self.assertGreater(self.web.requests, before)
        self.assertIs(self.manager.active_mode, ProtectionMode.PRIVACY_OVERLAY)

    def test_decoy_and_startup_preserve_application_gate(self):
        self.manager.set_automatic(True)
        window = MainWindow.__new__(MainWindow)
        window._closed = False
        window.controller = Mock(state=self.state)
        window.surface = self.surface
        window.web_opener = self.web
        window.protection = self.manager
        window.root = Mock()
        window.history_view = Mock()
        window._refresh_protection = Mock()
        window.application_settings = ApplicationSettings(True, (
            ProtectedApplication("Editor", r"C:\Apps\Editor.exe"),))
        window._last_external_application = ActiveApplication(r"C:\Apps\Editor.exe")
        window._foreground_detector = Mock()
        window._foreground_detector.detect.return_value = ActiveApplication(
            r"C:\Chrome\chrome.exe", process_id=123)
        window._poll_foreground_application()
        self.assertTrue(self.state.automatic_protection_requested)
        self.web.browser_pid = None
        self.web.starting = True
        window._poll_foreground_application()
        self.assertTrue(self.state.automatic_protection_requested)
        self.web.starting = False
        window._foreground_detector.detect.return_value = ActiveApplication(
            r"C:\Other\Other.exe", process_id=456)
        window._poll_foreground_application()
        self.assertFalse(self.state.automatic_protection_requested)


class BrowserWorkerTests(unittest.TestCase):
    def wait_for(self, predicate):
        until = monotonic() + 3
        while monotonic() < until:
            if predicate():
                return
            sleep(0.005)
        self.fail("Browser worker did not reach the expected state")

    def make_driver(self):
        driver = Mock()
        driver.current_window_handle = "decoy"
        driver.window_handles = ["decoy"]
        driver.capabilities = {"goog:processID": 123}
        return driver

    def worker(self, factory):
        web = StaticWebOpener(driver_factory=factory)
        web.CHECK_INTERVAL = 0.01
        web.RETRY_DELAY = 0.05
        def cleanup():
            web.shutdown()
            if web._thread is not None:
                web._thread.join(3)
                self.assertFalse(web._thread.is_alive())
        self.addCleanup(cleanup)
        return web

    def test_open_and_close_return_while_browser_startup_is_blocked(self):
        entered, release = Event(), Event()
        driver = self.make_driver()
        def create():
            entered.set()
            if not release.wait(3):
                raise RuntimeError("Test startup was not released")
            return driver
        web = self.worker(create)
        self.addCleanup(release.set)
        web.open()
        self.assertTrue(entered.wait(2))
        self.assertFalse(web.ready)
        web.close()
        release.set()
        self.wait_for(lambda: driver.quit.called)
        self.assertFalse(web.ready)
        self.assertIsNone(web.browser_pid)

    def test_closed_browser_is_detected_and_reopened(self):
        first, second = self.make_driver(), self.make_driver()
        factory = Mock(side_effect=[first, second])
        web = self.worker(factory)
        web.open()
        self.wait_for(lambda: web.ready)
        first.window_handles = []
        self.wait_for(lambda: web.last_error is not None)
        self.assertFalse(web.ready)
        self.wait_for(lambda: factory.call_count == 2 and web.ready)
        self.assertIsNone(web.last_error)
        self.assertEqual(web.browser_pid, 123)

    def test_startup_failure_can_retry(self):
        driver = self.make_driver()
        factory = Mock(side_effect=[RuntimeError("Chrome unavailable"), driver])
        web = self.worker(factory)
        web.open()
        self.wait_for(lambda: web.last_error is not None)
        self.assertFalse(web.ready)
        self.wait_for(lambda: web.ready)
        self.assertEqual(factory.call_count, 2)


if __name__ == "__main__":
    unittest.main()
