"""FR7.2 / FR7.4: opaque primary-display presentation; no content capture."""

import ctypes
import sys
import tkinter as tk

class TkProtectionSurface:
    """One reusable borderless topmost window; never an OS security boundary."""

    def __init__(self, root, close_app):
        self.root = root
        self._close_app = close_app
        self.window = None
        

    def show(self):
        if self.window is None:
            self.window = tk.Toplevel(self.root)
            self.window.withdraw()
            self.window.title('Red-Handed Protection')
            self.window.overrideredirect(True)
            self.window.attributes('-alpha', 1.0)
            self.window.attributes('-topmost', True)
            self.window.protocol('WM_DELETE_WINDOW', self._close_app)
            tk.Button(self.window, text='Exit Red-Handed', command=self._close_app).pack(side=tk.LEFT, padx=8)
        window = self.window
        window.configure(background = '#17202b')
        
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