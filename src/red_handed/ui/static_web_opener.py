"""Run browser operations in the background so the dashboard stays responsive."""

import logging
from pathlib import Path
from threading import Event, Lock, Thread
from time import monotonic


class StaticWebOpener:
    CHECK_INTERVAL = 0.25
    RETRY_DELAY = 2.0

    def __init__(self, *, driver_factory=None):
        self._html_path = Path(__file__).with_name("index.html")
        self._driver_factory = driver_factory
        self._lock = Lock()
        self._wake = Event()
        self._thread = None
        self._wanted = False
        self._closed = False
        self._version = 0
        self._ready = False
        self._starting = False
        self._browser_pid = None
        self._last_error = None

    @property
    def ready(self):
        with self._lock:
            return self._ready

    @property
    def starting(self):
        with self._lock:
            return self._starting

    @property
    def browser_pid(self):
        with self._lock:
            return self._browser_pid

    @property
    def last_error(self):
        with self._lock:
            return self._last_error

    def open(self):
        with self._lock:
            if self._closed:
                raise RuntimeError("The decoy browser worker is closed.")
            changed = not self._wanted
            if changed:
                self._wanted = True
                self._version += 1
                self._starting = True
                self._last_error = None
            if self._thread is None:
                self._thread = Thread(target=self._run, name="decoy-browser", daemon=True)
                self._thread.start()
        if changed:
            self._wake.set()

    def close(self):
        with self._lock:
            if self._wanted:
                self._version += 1
            self._wanted = False
            self._ready = self._starting = False
            self._browser_pid = self._last_error = None
        self._wake.set()

    def shutdown(self):
        self.close()
        with self._lock:
            self._closed = True
        self._wake.set()
        # Give Chrome a chance to close without holding up exit indefinitely.
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _publish(self, version, *, ready, starting=False, pid=None, error=None):
        with self._lock:
            if self._wanted and not self._closed and version == self._version:
                self._ready, self._starting = ready, starting
                self._browser_pid, self._last_error = pid, error

    def _create_driver(self):
        if self._driver_factory is not None:
            return self._driver_factory()
        # Other protection modes should work even if Selenium is missing.
        from selenium import webdriver
        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        return webdriver.Chrome(options=options)

    @staticmethod
    def _quit(driver):
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                logging.getLogger(__name__).exception("Could not close the decoy browser")

    def _run(self):
        driver = None
        driver_version = None
        retry_at = 0.0
        try:
            while True:
                with self._lock:
                    wanted, closed, version = self._wanted, self._closed, self._version

                if closed or not wanted or (driver is not None and driver_version != version):
                    self._quit(driver)
                    driver = None
                    retry_at = 0.0
                if closed:
                    return

                if wanted:
                    try:
                        if driver is None and monotonic() >= retry_at:
                            self._publish(version, ready=False, starting=True)
                            driver = self._create_driver()
                            driver_version = version
                            pid = driver.capabilities.get("goog:processID")
                            self._publish(version, ready=False, starting=True, pid=pid)
                            driver.set_page_load_timeout(15)
                            driver.get(self._html_path.resolve().as_uri())
                            handle = driver.current_window_handle
                            if handle not in driver.window_handles:
                                raise RuntimeError("The decoy browser window was closed.")
                            self._publish(version, ready=True, pid=pid)
                        elif driver is not None:
                            if handle not in driver.window_handles:
                                raise RuntimeError("The decoy browser window was closed.")
                    except Exception as error:
                        self._publish(version, ready=False, error=str(error))
                        self._quit(driver)
                        driver = None
                        retry_at = monotonic() + self.RETRY_DELAY

                self._wake.wait(self.CHECK_INTERVAL)
                self._wake.clear()
        finally:
            self._quit(driver)
