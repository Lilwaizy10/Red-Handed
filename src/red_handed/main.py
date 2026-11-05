"""Application startup for Red-Handed."""

import tkinter as tk

from red_handed.core.monitoring import MonitoringController
from red_handed.ui.main_window import MainWindow


def main() -> None:
    """Start the dashboard and clean up the resources that were created."""
    root = tk.Tk()
    controller = None
    window = None

    try:
        controller = MonitoringController()
        window = MainWindow(root, controller)
        root.mainloop()
    finally:
        if window is not None:
            # MainWindow owns hotkeys, protection, timers, and controller cleanup.
            # Its close() method is safe after the normal X-button close.
            window.close()
        else:
            # Construction failed before ownership passed to a complete window.
            try:
                if controller is not None:
                    controller.close()
            finally:
                try:
                    root.destroy()
                except tk.TclError:
                    # The window may already have cleaned up and destroyed Tk.
                    pass


if __name__ == "__main__":
    main()