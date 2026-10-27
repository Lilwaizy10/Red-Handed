"""Check startup and cleanup without creating windows or native resources."""

from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from red_handed.main import main
from red_handed.ui.main_window import MainWindow


class StartupTests(unittest.TestCase):
    def test_startup_delegates_cleanup_to_window(self) -> None:
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
        root.after_idle.assert_not_called()
        window.close.assert_called_once()

        # The real window performs these operations; startup must not duplicate them.
        controller.close.assert_not_called()
        root.destroy.assert_not_called()

    def test_failed_window_construction_cleans_controller_and_root(self) -> None:
        root = Mock()
        controller = Mock()

        with (
            patch("red_handed.main.tk.Tk", return_value=root),
            patch(
                "red_handed.main.MonitoringController",
                return_value=controller,
            ),
            patch(
                "red_handed.main.MainWindow",
                side_effect=RuntimeError("Window construction failed."),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "construction failed"):
                main()

        controller.close.assert_called_once()
        root.destroy.assert_called_once()
        root.mainloop.assert_not_called()


if __name__ == "__main__":
    unittest.main()