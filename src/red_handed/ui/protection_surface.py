"""FR7.2 / FR7.4: opaque primary-display presentation; no content capture."""

import ctypes
import sys
import tkinter as tk

from red_handed.core.settings import ProtectionMode


class TkProtectionSurface:
    """One reusable borderless topmost window; never an OS security boundary."""

    def __init__(self, root, toggle_manual, stop_monitoring, close_app, dismiss_test):
        self.root = root
        self._toggle_manual, self._stop_monitoring = toggle_manual, stop_monitoring
        self._close_app, self._dismiss_test = close_app, dismiss_test
        self.window = None
        self.title = self.details = self.controls = None
        self.hotkey_hint = 'Use the configured emergency hotkey to toggle manual protection.'

    def show(self, mode, *, test=False, source=''):
        # Accept the enum or its text value, and fail early on anything else.
        mode = ProtectionMode(mode)
        if self.window is None:
            self.window = tk.Toplevel(self.root)
            try:
                self.window.withdraw()
                self.window.title('Red-Handed Protection')
                self.window.overrideredirect(True)
                self.window.attributes('-alpha', 1.0)
                self.window.attributes('-topmost', True)
                self.window.protocol('WM_DELETE_WINDOW', self._close_app)
                self.title = tk.Label(self.window, font=('Segoe UI', 26, 'bold'))
                self.title.pack(expand=True)
                self.details = tk.Label(self.window, font=('Segoe UI', 11), wraplength=800)
                self.details.pack(pady=8)
                self.controls = tk.Frame(self.window)
                self.controls.pack(pady=(0, 20))
            except Exception:
                # Never reuse a partially configured window.
                self.close()
                raise
        window = self.window
        background = '#000000' if mode is ProtectionMode.SCREEN_BLACKOUT else '#17202b'
        window.configure(background=background)
        self.controls.configure(background=background)
        # Join lines instead of concatenating strings so a blackout test screen
        # doesn't show a trailing space on the second line. The text is short
        # enough that we don't need to wrap it, but if we did, the space would
        # be visible.
        title_lines = []
        if test:
            title_lines.append('TEST MODE')
        if mode is ProtectionMode.PRIVACY_OVERLAY:
            title_lines += ['Red-Handed', 'What you looking at?']
        self.title.configure(background=background, foreground='white', text='\n'.join(title_lines))
        self.details.configure(background=background, foreground='#d1d5db',
            text=f"{'TEST MODE - closes after 5 seconds' if test else 'Protection active: ' + source}\n"
                 f"{mode.value} | {self.hotkey_hint}")
        for widget in self.controls.winfo_children():
            widget.destroy()
        if test:
            tk.Button(self.controls, text='Dismiss Test', command=self._dismiss_test).pack(side=tk.LEFT, padx=8)
        else:
            tk.Button(self.controls, text='Toggle Manual Protection', command=self._toggle_manual).pack(side=tk.LEFT, padx=8)
            tk.Button(self.controls, text='Stop Monitoring / Clear Automatic',
                      command=self._stop_monitoring).pack(side=tk.LEFT, padx=8)
        tk.Button(self.controls, text='Exit Red-Handed', command=self._close_app).pack(side=tk.LEFT, padx=8)
        # Primary display only (FUT5 is not implemented). Use the full display,
        # not its work area, so the taskbar region is covered as well.
        if sys.platform == 'win32':
            user32 = ctypes.WinDLL('user32')
            width, height = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        else:
            raise OSError('Protection surfaces are supported only on Windows.')
        window.geometry(f'{width}x{height}+0+0')
        window.deiconify()
        window.lift()
        window.update_idletasks()

    def hide(self):
        if self.window is not None:
            self.window.withdraw()

    def close(self):
        if self.window is not None:
            self.window.destroy()
            self.window = None
            # The child widgets were destroyed with the window; drop the stale references.
            self.title = self.details = self.controls = None
