"""Check startup wiring without opening a desktop window or camera."""

from red_handed.ui.main_window import MainWindow
from red_handed.main import main
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))


class StartupTests(unittest.TestCase):
    def test_startup_uses_current_window_interface(self) -> None:
        root = Mock()
        controller = Mock()

        window = Mock(spec=MainWindow)

        with (
            patch("red_handed.main.tk.Tk", return_value=root),
            patch(
                "red_handed.main.MonitoringController",
                return_value=controller,
            ),
            patch(
                "red_handed.main.MainWindow",
                return_value=window,
            ) as create_window,
        ):
            main()

        create_window.assert_called_once_with(root, controller)
        root.mainloop.assert_called_once()

        # MainWindow now schedules its own initial camera check.
        root.after_idle.assert_not_called()

        controller.close.assert_called_once()
        root.destroy.assert_called_once()


if __name__ == "__main__":
    unittest.main()
