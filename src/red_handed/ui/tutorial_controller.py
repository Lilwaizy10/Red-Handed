"""In-memory navigation for the setup guide; never changes app settings."""

from dataclasses import dataclass, replace
from typing import Callable


@dataclass(frozen=True)
class TutorialStep:
    title: str
    instruction: str
    target: str
    next_enabled: bool = False
    next_label: str = "Next"
    alternate_label: str | None = None


@dataclass(frozen=True)
class TutorialContext:
    camera_available: bool = False
    monitoring: bool = False
    preview_ready: bool = False
    zone_open: bool = False
    saved_zone: bool = False
    draft_ready: bool = False
    preview_error: bool = False

    @property
    def camera_ready(self) -> bool:
        return self.camera_available and self.monitoring and self.preview_ready


SETUP_STEPS = (
    TutorialStep(
        "Start the camera",
        "Click Start Monitoring. The guide continues when the live camera preview appears.",
        "start_monitoring",
    ),
    TutorialStep(
        "Open zone setup",
        "Click Privacy Zone Setup in the sidebar to choose the area Red-Handed watches.",
        "privacy_zone",
    ),
    TutorialStep(
        "Draw your privacy zone",
        "Click and drag inside the camera image around the area where another person might appear. "
        "A plain click or dragging outside the image does not create a zone.",
        "preview",
    ),
    TutorialStep(
        "Save your zone",
        "The dashed yellow rectangle is not saved yet. Click Save Zone to use it for monitoring. "
        "Any saved zone stays in use until saving succeeds.",
        "save_zone",
    ),
    TutorialStep(
        "Choose screen protection",
        "Click Protection Mode to choose how your screen is covered and save any changes. "
        "You can keep the current settings.",
        "protection_mode",
        next_enabled=True,
        next_label="Close guide",
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
        self.context = TutorialContext()
        self._reviewing = False
        self._redraw = False
        self._save_failed = False
        self._last_render = None

    @property
    def active(self) -> bool:
        return self.index is not None

    def start(self, context: TutorialContext | None = None) -> None:
        self.index = 0
        self.context = context or TutorialContext()
        self._reviewing = self._redraw = self._save_failed = False
        self._last_render = None
        self.update(self.context)

    def update(self, context: TutorialContext) -> None:
        self.context = context
        if not self.active:
            return
        if self.index in (1, 2, 3) and not context.camera_ready:
            self.index = 0
            self._reviewing = False
        elif self.index in (2, 3) and not context.zone_open:
            self.index = 1
            self._reviewing = False
        if not self._reviewing:
            if self.index == 0 and context.camera_ready:
                self.index = 1
            if self.index == 1 and context.zone_open and context.camera_ready:
                self.index = 2
            if self.index == 2 and context.draft_ready:
                self.index = 3
            elif self.index == 3 and not context.draft_ready:
                self.index = 2
                self._save_failed = False
        self._render()

    def next(self) -> None:
        if self.index is None or not self._step().next_enabled:
            return
        if self.index == len(SETUP_STEPS) - 1:
            self.skip()
        else:
            # Keeping an existing zone is an explicit choice, never an automatic skip.
            self.index = 4 if self.index == 2 and not self.context.draft_ready else self.index + 1
            self._reviewing = False
            self.update(self.context)

    def back(self) -> None:
        if self.index is not None and self.index > 0:
            self.index = 2 if self.index == 4 else self.index - 1
            self._reviewing = True
            self._redraw = self._save_failed = False
            self._render()

    def redraw(self) -> None:
        if self.index == 2 and self.context.saved_zone and not self.context.draft_ready:
            self._redraw = True
            self._reviewing = False
            self._render()

    def zone_saved(self, context: TutorialContext) -> None:
        if self.index in (2, 3) and context.camera_ready and context.zone_open and context.saved_zone:
            self.index = 4
            self._reviewing = self._save_failed = False
        self.update(context)

    def save_failed(self) -> None:
        if self.index == 3:
            self._save_failed = True
            self._render()

    def skip(self) -> None:
        if self.active:
            self.index = None
            self._last_render = None
            self._hide()

    def _step(self) -> TutorialStep:
        step = SETUP_STEPS[self.index]
        context = self.context
        if self.index == 0:
            if context.camera_ready:
                return replace(step, instruction="The live camera preview is ready. Choose Next to continue.",
                               next_enabled=True)
            if not context.camera_available:
                return replace(step, target="retry_camera", instruction=
                    "Click Retry Camera Access. Check that your camera is connected and camera access is allowed, "
                    "then click Start Monitoring when it becomes available.")
            if context.monitoring and not context.preview_ready:
                if context.preview_error:
                    return replace(step, target="stop_monitoring", instruction=
                        "The camera preview could not be displayed. Click Stop Monitoring, then start it again.")
                return replace(step, target="preview", instruction=
                    "Waiting for the live camera preview. The guide will continue when an image is displayed.")
            return replace(step, next_enabled=context.camera_ready)
        if self.index == 1:
            return replace(step, next_enabled=context.zone_open and context.camera_ready)
        if self.index == 2:
            if context.saved_zone and not context.draft_ready and not self._redraw:
                return replace(step, title="Use your saved zone", target="preview",
                    instruction="The solid blue zone is already loaded and used for monitoring. "
                    "Choose Keep this zone, or Draw a replacement to change it.",
                    next_enabled=True, next_label="Keep this zone", alternate_label="Draw a replacement")
            return replace(step, next_enabled=context.draft_ready)
        if self.index == 3 and self._save_failed:
            return replace(step, instruction="Your zone was not saved. Check the error below and retry Save Zone. "
                "Your draft has been kept; any saved zone is unchanged.")
        return step

    def _render(self) -> None:
        if self.index is not None:
            rendered = (self._step(), self.index, len(SETUP_STEPS))
            if rendered != self._last_render:
                self._last_render = rendered
                self._show_step(*rendered)
