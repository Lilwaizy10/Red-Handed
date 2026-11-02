import logging
import os
import sys

from red_handed.core.applications import ActiveApplication

# Module-level logger. Low-level failure details (Win32 error codes, unexpected
# exceptions) go here, while the ActiveApplication result keeps short, stable
# error messages that the rest of the app can display or compare against.
logger = logging.getLogger(__name__)

# Win32 constants, named so the magic numbers are self-explanatory.
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000  # Works on most processes without admin rights.
GA_ROOT = 2  # GetAncestor flag: walk up to the top-level (root) window.
MAX_PATH_CHARS = 32768  # Maximum path length Windows supports (long paths).

# Common Win32 error codes, used only to make log lines readable.
ERROR_ACCESS_DENIED = 5  # Elevated/protected process we are not allowed to open.
ERROR_INVALID_PARAMETER = 87  # Usually means the process has already exited.


class WindowsForegroundBackend:
    """Thin ctypes wrapper around the Win32 calls needed to inspect the foreground window."""

    def __init__(self):
        if sys.platform != 'win32':
            raise OSError('Foreground application detection requires Windows.')
        import ctypes
        from ctypes import wintypes as w
        self.ctypes = ctypes
        # use_last_error=True gives this module its own copy of the Win32 "last error",
        # which we read with ctypes.get_last_error() right after a failed call.
        self.user32 = ctypes.WinDLL('user32', use_last_error=True)
        self.kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

        # Declaring argtypes/restype is important: without them ctypes assumes
        # 32-bit ints, which can truncate 64-bit handles (HWND/HANDLE).
        self.user32.GetForegroundWindow.argtypes = []
        self.user32.GetForegroundWindow.restype = w.HWND
        self.user32.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
        self.user32.GetWindowThreadProcessId.restype = w.DWORD
        # GetAncestor lets us find the top-level window that owns a child window.
        self.user32.GetAncestor.argtypes = [w.HWND, w.UINT]
        self.user32.GetAncestor.restype = w.HWND
        self.kernel32.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        self.kernel32.OpenProcess.restype = w.HANDLE
        self.kernel32.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
        self.kernel32.QueryFullProcessImageNameW.restype = w.BOOL
        self.kernel32.CloseHandle.argtypes = [w.HANDLE]
        self.kernel32.CloseHandle.restype = w.BOOL
        self.w = w

    def foreground_window(self):
        """Return the handle of the window the user is currently interacting with (0/None if none)."""
        return self.user32.GetForegroundWindow()

    def root_window(self, hwnd):
        """Return the top-level window that contains hwnd.

        If hwnd is already top-level (or the lookup fails) this returns hwnd itself,
        so callers can always compare the result safely.
        """
        root = self.user32.GetAncestor(hwnd, GA_ROOT)
        return root or hwnd

    def process_id_for_window(self, hwnd):
        """Return the ID of the process that owns hwnd."""
        pid = self.w.DWORD()
        # The return value of GetWindowThreadProcessId is the *thread* ID, not a
        # success flag. A return of 0 means the call failed (e.g. window already gone),
        # which is why we check both the return value and pid.value.
        if not self.user32.GetWindowThreadProcessId(hwnd, self.ctypes.byref(pid)) or not pid.value:
            raise OSError('Foreground process unavailable.')
        return pid.value

    def executable_for_window(self, hwnd):
        """Return the full path of the executable that owns hwnd."""
        pid = self.process_id_for_window(hwnd)

        handle = self.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            # Read the error code immediately; any other Win32 call could overwrite it.
            code = self.ctypes.get_last_error()
            if code == ERROR_ACCESS_DENIED:
                logger.debug('OpenProcess denied for pid %s (elevated or protected process).', pid)
            elif code == ERROR_INVALID_PARAMETER:
                logger.debug('OpenProcess failed for pid %s (process likely exited).', pid)
            else:
                logger.debug('OpenProcess failed for pid %s with Win32 error %s.', pid, code)
            raise OSError('Foreground process cannot be queried.')
        try:
            # size is in/out: we pass the buffer capacity, Windows writes back the path length.
            size = self.w.DWORD(MAX_PATH_CHARS)
            buffer = self.ctypes.create_unicode_buffer(size.value)
            if not self.kernel32.QueryFullProcessImageNameW(handle, 0, buffer, self.ctypes.byref(size)):
                logger.debug('QueryFullProcessImageNameW failed for pid %s with Win32 error %s.',
                             pid, self.ctypes.get_last_error())
                raise OSError('Foreground executable unavailable.')
            return buffer.value
        finally:
            # Always release the handle, whether we succeeded or raised above.
            self.kernel32.CloseHandle(handle)


class ActiveApplicationDetector:
    """Determines which application is in the foreground, without ever raising."""

    def __init__(self, backend=None):
        self.backend = backend if backend is not None else WindowsForegroundBackend()

    def _is_protection_surface(self, hwnd, protection_window):
        """True if hwnd belongs to our own protection UI.

        Three checks, from cheapest to broadest:
        1. Exact handle match (the original check).
        2. Same top-level window: covers the case where the foreground handle is a
           child control of the protection window rather than the window itself.
        3. Same process as us: covers extra windows we own (popups, secondary
           overlays) and the case where protection_window is not set yet. Our own
           process should never be reported as a regular monitored application.
        Checks 2 and 3 only run if the backend provides the matching methods, so
        simple test fakes that only implement the original methods keep working.
        """
        if protection_window and hwnd == protection_window:
            return True

        root_window = getattr(self.backend, 'root_window', None)
        if protection_window and root_window is not None:
            if root_window(hwnd) == root_window(protection_window):
                return True

        process_id_for_window = getattr(self.backend, 'process_id_for_window', None)
        if process_id_for_window is not None:
            if process_id_for_window(hwnd) == os.getpid():
                return True

        return False

    def detect(self, protection_window=None):
        """Return an ActiveApplication describing the current foreground window.

        Doesn't raise: every failure is converted into ActiveApplication(error=...).
        """
        try:
            hwnd = self.backend.foreground_window()
            if not hwnd:
                # Happens on the desktop, during window switches, and on secure
                # desktops (UAC prompt, lock screen).
                return ActiveApplication(error='No foreground application.')

            # Check for our own UI before looking up the executable so we never
            # report ourselves as the app being monitored.
            if self._is_protection_surface(hwnd, protection_window):
                return ActiveApplication(protection_surface=True)

            pid = self.backend.process_id_for_window(hwnd)
            path = self.backend.executable_for_window(hwnd)

            # The user may have switched windows while we were querying. In that case
            # the path we found belongs to the old window (and a reused PID could even
            # point at a different process), so discard it rather than report stale data.
            if self.backend.foreground_window() != hwnd:
                return ActiveApplication(error='Foreground changed during detection.')
            if not path:
                return ActiveApplication(error='Foreground executable unavailable.')
            return ActiveApplication(executable_path=path, process_id=pid)
        except OSError as exc:
            # Expected failures: inaccessible, elevated, or already-exited processes.
            # Keep the user-facing message generic and log the specifics.
            logger.debug('Foreground detection failed: %s', exc)
            return ActiveApplication(error='Foreground application unavailable.')
        except Exception:
            # Unexpected failure. Still honor the "never raises"
            # contract, but log the full traceback so it doesn't disappear.
            logger.exception('Unexpected error during foreground detection.')
            return ActiveApplication(error='Foreground application unavailable.')