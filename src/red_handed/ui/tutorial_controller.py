"""In-memory navigation for the setup guide; never changes app settings."""

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class TutorialStep:
    title: str
    instruction: str
    target: str


SETUP_STEPS = (
    TutorialStep(
        "Start the camera",
        "Click Start Monitoring to see your camera preview. If unavailable, use Retry Camera Access. "
        "Then choose Next.",
        "start_monitoring",
    ),
    TutorialStep(
        "Set your privacy zone",
        "Click Privacy Zone Setup. Keep your saved zone, or drag inside the live preview "
        "and click Save Zone. Then choose Next.",
        "privacy_zone",
    ),
    TutorialStep(
        "Choose screen protection",
        "Click Protection Mode to choose how your screen is covered and save any changes. "
        "You can keep the current settings.",
        "protection_mode",
    ),
)


class TutorialController:
    """Navigate guide steps without starting cameras, saving, or opening panels."""

    def __init__(
        self,
        show_step: Callable[[TutorialStep, int, int], None],
        hide: Callable[[], None],
    ) -> None:
        self._show_step = show_step
        self._hide = hide
        self.index: int | None = None

    @property
    def active(self) -> bool:
        return self.index is not None

    def start(self) -> None:
        self.index = 0
        self._render()

    def next(self) -> None:
        if self.index is None:
            return
        if self.index == len(SETUP_STEPS) - 1:
            self.skip()
        else:
            self.index += 1
            self._render()

    def back(self) -> None:
        if self.index is not None and self.index > 0:
            self.index -= 1
            self._render()

    def skip(self) -> None:
        if self.active:
            self.index = None
            self._hide()

    def _render(self) -> None:
        if self.index is not None:
            self._show_step(SETUP_STEPS[self.index], self.index, len(SETUP_STEPS))
