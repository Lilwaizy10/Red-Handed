"""Convenient repository-root launcher for Red-Handed."""

from pathlib import Path
import sys


SOURCE_DIRECTORY = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(SOURCE_DIRECTORY))

from red_handed.main import main  # noqa: E402


if __name__ == "__main__":
    main()