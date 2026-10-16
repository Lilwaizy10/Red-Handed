"""Application startup for Red-Handed."""

import tkinter as tk

from red_handed.core.monitoring import MonitoringController
from red_handed.ui.main_window import MainWindow


def main() -> None:
    """Create one controller and connect it to the desktop dashboard."""
    root = tk.Tk()
    controller = MonitoringController()

    try:
        window = MainWindow(root, controller)

        # Let Tk construct the interface before checking the camera.
        root.after_idle(window.initialize)
        root.mainloop()
    finally:
        # Also clean up if startup fails or the event loop exits unexpectedly.
        # Controller.close() is safe to call more than once.
        try:
            controller.close()
        finally:
            try:
                root.destroy()
            except tk.TclError:
                # The normal window-close handler may already have destroyed Tk.
                pass


if __name__ == "__main__":
    main()