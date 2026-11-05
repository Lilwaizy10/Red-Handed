"""FR10: validated hotkeys, transactional replacement and a Windows backend."""

from concurrent.futures import Future
from dataclasses import dataclass
from queue import Empty, Queue
import sys
from threading import Event, Thread
from time import perf_counter


@dataclass(frozen=True)
class Hotkey:
    text: str
    modifiers: int
    key: int


def parse_hotkey(text: str) -> Hotkey:
    """Deliberately bounded grammar: Ctrl/Alt/Shift plus A-Z, 0-9 or F1-F11."""
    if not isinstance(text, str):
        raise ValueError("Hotkey must be text, for example Ctrl+Alt+P.")
    parts = [part.strip().upper() for part in text.split('+')]
    modifiers = {'CTRL': 2, 'ALT': 1, 'SHIFT': 4}
    if (len(parts) < 2 or len(set(parts)) != len(parts)
            or any(part not in modifiers for part in parts[:-1])):
        raise ValueError("Use Ctrl/Alt/Shift plus a letter, digit or F1-F11.")
    # Avoid intercepting ordinary typing, F12/debugger and reserved Win shortcuts.
    if not {'CTRL', 'ALT'} & set(parts[:-1]):
        raise ValueError("Include Ctrl or Alt; Shift alone is not an emergency shortcut.")
    key = parts[-1]
    if len(key) == 1 and key in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789':
        vk = ord(key)
    elif key in [f'F{i}' for i in range(1, 12)]:
        vk = 0x70 + int(key[1:]) - 1
    else:
        raise ValueError("The final key must be A-Z, 0-9 or F1-F11 (F12 is reserved).")
    if set(parts) == {'ALT', 'F4'}:
        raise ValueError("Alt+F4 is reserved for closing windows.")
    ordered = [name.title() for name in modifiers if name in parts[:-1]]
    return Hotkey('+'.join(ordered + [key]), sum(modifiers[p] for p in parts[:-1]), vk)


class WindowsHotkeyBackend:
    """Own RegisterHotKey and its message queue on one dedicated Windows thread.

    Only hotkey IDs cross to Tk; no keyboard hook, key logging, elevated access,
    or third-party package. The worker never touches a Tk widget.
    """

    def __init__(self):
        if sys.platform != 'win32':
            raise OSError("Global hotkeys are supported only on Windows.")
        import ctypes
        from ctypes import wintypes
        self._ctypes, self._wintypes = ctypes, wintypes
        self._user32 = ctypes.WinDLL('user32', use_last_error=True)
        self._user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        self._user32.RegisterHotKey.restype = wintypes.BOOL
        self._user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        self._user32.UnregisterHotKey.restype = wintypes.BOOL
        self._user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                            wintypes.UINT, wintypes.UINT, wintypes.UINT]
        self._user32.PeekMessageW.restype = wintypes.BOOL
        self._commands, self._events = Queue(), Queue()
        self._stop = Event()
        self._thread = Thread(target=self._run, name='red-handed-hotkey', daemon=True)
        self._thread.start()

    def _run(self):
        registered = set()
        message = self._wintypes.MSG()
        try:
            while not self._stop.is_set():
                try:
                    action, identifier, spec, future = self._commands.get(timeout=.01)
                except Empty:
                    pass
                else:
                    try:
                        if action == 'register':
                            ok = bool(self._user32.RegisterHotKey(None, identifier,
                                      spec.modifiers | 0x4000, spec.key))  # MOD_NOREPEAT
                            if ok:
                                registered.add(identifier)
                        else:
                            ok = bool(self._user32.UnregisterHotKey(None, identifier))
                            if ok:
                                registered.discard(identifier)
                        future.set_result(ok)
                    except Exception as error:
                        future.set_exception(error)
                while self._user32.PeekMessageW(self._ctypes.byref(message), None, 0x0312, 0x0312, 1):
                    if message.message == 0x0312:
                        self._events.put((int(message.wParam), perf_counter()))
        finally:
            for identifier in registered:
                self._user32.UnregisterHotKey(None, identifier)

    def _call(self, action, identifier, spec=None):
        if self._stop.is_set() or not self._thread.is_alive():
            raise OSError("Hotkey service is closed.")
        future = Future()
        self._commands.put((action, identifier, spec, future))
        return future.result(timeout=2)

    def register(self, identifier, spec):
        return self._call('register', identifier, spec)

    def unregister(self, identifier):
        return self._call('unregister', identifier)

    def drain(self):
        events = []
        while True:
            try:
                events.append(self._events.get_nowait())
            except Empty:
                return events

    def close(self):
        self._stop.set()
        self._thread.join(timeout=2)
        if self._thread.is_alive():
            raise OSError("Hotkey service did not stop.")


class HotkeyManager:
    """Register candidate before releasing old binding; failed saves can roll back."""

    def __init__(self, backend, callback):
        self.backend, self.callback = backend, callback
        self.current: Hotkey | None = None
        self._current_id = None
        self._pending = None
        self._next_id = 1
        self.last_dispatch_seconds = None

    def prepare(self, text):
        spec = parse_hotkey(text)
        if self._pending is not None:
            raise ValueError("A hotkey change is already pending.")
        if spec == self.current:
            return
        identifier = self._next_id
        self._next_id = 1 if identifier >= 0xBFFF else identifier + 1
        if not self.backend.register(identifier, spec):
            raise ValueError("Hotkey is reserved or in use. The previous hotkey remains active.")
        self._pending = (identifier, spec)

    def commit(self):
        if self._pending is None:
            return
        old_id = self._current_id
        self._current_id, self.current = self._pending
        self._pending = None
        if old_id is not None:
            self.backend.unregister(old_id)

    def rollback(self):
        if self._pending is not None:
            self.backend.unregister(self._pending[0])
            self._pending = None

    def configure(self, text):
        self.prepare(text)
        self.commit()

    def poll(self):
        for event in self.backend.drain():
            identifier, received = event if isinstance(event, tuple) else (event, perf_counter())
            if identifier == self._current_id:
                self.callback()
                self.last_dispatch_seconds = perf_counter() - received

    def close(self):
        try:
            self.rollback()
            if self._current_id is not None:
                self.backend.unregister(self._current_id)
        finally:
            self._current_id, self.current = None, None
            self.backend.close()