"""In-memory navigation for the setup guide; never changes app settings."""

from dataclasses import dataclass, replace
from typing import Callable


@dataclass(frozen=True)
class TutorialStep:
    title: str
    instruction: str
    target: str | None
    next_enabled: bool = False
    next_label: str = "Next"
    alternate_label: str | None = None
    back_enabled: bool = True


@dataclass(frozen=True)
class TutorialContext:
    camera_available: bool = False
    monitoring: bool = False
    preview_ready: bool = False
    zone_open: bool = False
    saved_zone: bool = False
    draft_ready: bool = False
    preview_error: bool = False
    protection_open: bool = False
    protection_dirty: bool = False
    protection_save_failed: bool = False
    home_open: bool = False
    selected_mode: str = "Privacy Overlay"
    hotkey: str = "Ctrl+Alt+P"
    hotkey_available: bool = False
    test_requested: bool = False
    automatic_requested: bool = False
    manual_requested: bool = False
    protection_active: bool = False
    actual_mode: str = ""
    protection_error: str = ""
    runtime_summary: str = ""

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
        "Click Protection Mode in the sidebar to choose how your primary display is covered.",
        "protection_mode",
    ),
    TutorialStep(
        "Preview your protection",
        "Click Home, then Test Protection (5 seconds). It covers your screen briefly; "
        "you can dismiss it early. A preview does not turn on monitoring.",
        "home",
    ),
    TutorialStep(
        "Setup walkthrough complete",
        "",
        None,
        next_enabled=True,
        next_label="Finish",
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
        self._reset_preview()

    @property
    def active(self) -> bool:
        return self.index is not None

    def start(self, context: TutorialContext | None = None) -> None:
        self.index = 0
        self.context = context or TutorialContext()
        self._reviewing = self._redraw = self._save_failed = False
        self._last_render = None
        self._reset_preview()
        self.update(self.context)

    def update(self, context: TutorialContext) -> None:
        self.context = context
        if not self.active:
            return
        if self.index in (5, 6) and context.protection_dirty:
            self.index = 4
            self._reset_preview()
        if self.index == 5 and self._test_in_progress:
            if context.test_requested:
                if context.protection_error or not context.protection_active:
                    self._test_failed = True
                    self._test_failure_reason = context.protection_error or "Protection was not displayed."
                elif context.actual_mode:
                    self._test_observed = True
                    self._test_failed = False
                    self._test_failure_reason = ""
                    self._preview_result = context.actual_mode
                    if context.actual_mode != context.selected_mode:
                        self._preview_result += f" (fallback for {context.selected_mode})"
            elif context.automatic_requested or context.manual_requested:
                self._test_interrupted = True
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
            if self.index == 5:
                self._reset_preview()
            self._reviewing = False
            self.update(self.context)

    def back(self) -> None:
        if self._test_in_progress:
            return
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

    def protection_saved(self, context: TutorialContext) -> None:
        if self.index in (4, 5, 6) and context.protection_open and not context.protection_dirty:
            self.index = 5
            self._reviewing = False
            self._reset_preview()
        self.update(context)

    def test_started(self, context: TutorialContext) -> None:
        if self.index == 5 and context.test_requested:
            self._reset_preview()
            self._test_in_progress = True
        self.update(context)

    def test_finished(self, context: TutorialContext) -> None:
        if self.index == 5 and self._test_in_progress:
            self._test_in_progress = False
            self._test_interrupted |= context.automatic_requested or context.manual_requested
            if (self._test_observed and not self._test_failed and not self._test_interrupted
                    and not context.test_requested and not context.protection_error):
                self._preview_complete = True
                self.index = 6
                self._reviewing = False
        self.update(context)

    def _reset_preview(self) -> None:
        self._test_in_progress = self._test_observed = self._test_failed = False
        self._test_interrupted = self._preview_complete = False
        self._preview_result = ""
        self._test_failure_reason = ""

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
        if self.index == 4 and context.protection_open:
            if context.protection_save_failed:
                return replace(step, target="save_protection", instruction=
                    "Protection settings were not saved. Check the error below and retry Save Protection Settings, "
                    "or Discard changes to keep the saved settings.")
            if context.protection_dirty:
                return replace(step, target="save_protection", instruction=
                    "Click Save Protection Settings to apply your changes, or Discard changes to keep the saved settings.")
            return replace(step, target="protection_choices", next_enabled=True, next_label="Keep current settings",
                instruction="Choose a mode below and click Save Protection Settings. "
                "Or choose Keep current settings to use the saved mode and shortcut.")
        if self.index == 5:
            if self._test_in_progress or context.test_requested:
                return replace(step, target=None, back_enabled=False,
                    instruction="The five-second preview is running. Use Dismiss Test or your shortcut to end it early. "
                    "Real protection requests stay in place.")
            if context.automatic_requested or context.manual_requested:
                return replace(step, target=None, instruction=
                    "Real protection is already active. A preview can run when those requests have cleared. "
                    "You can skip the guide without changing protection.")
            if self._preview_complete:
                return replace(step, target=None, next_enabled=True, next_label="View summary",
                    instruction=f"Preview showed {self._preview_result}. Choose View summary or run another preview.")
            if self._test_failed or self._test_interrupted or context.protection_error:
                reason = self._test_failure_reason or context.protection_error
                if self._test_interrupted:
                    reason = "A real protection request interrupted the preview."
                return replace(step, target="test_protection" if context.home_open else "home",
                    instruction=f"The preview did not complete successfully. {reason} "
                    "Return Home and retry Test Protection (5 seconds).")
            if context.home_open:
                return replace(step, target="test_protection", instruction=
                    "Click Test Protection (5 seconds). Your screen is covered briefly; use Dismiss Test or your "
                    "shortcut to end it early. Monitoring is unchanged.")
        if self.index == 6:
            shortcut = context.hotkey + ("" if context.hotkey_available else " (check shortcut status)")
            summary = (
                f"Zone: {'saved and loaded' if context.saved_zone else 'not configured'}. "
                f"Mode: {context.selected_mode}. Shortcut: {shortcut}.\n"
                f"Preview showed {self._preview_result}.\n{context.runtime_summary}"
            )
            return replace(step, instruction=summary)
        return step

    def _render(self) -> None:
        if self.index is not None:
            rendered = (self._step(), self.index, len(SETUP_STEPS))
            if rendered != self._last_render:
                self._last_render = rendered
                self._show_step(*rendered)
