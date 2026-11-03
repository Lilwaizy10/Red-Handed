"""Optional guides using the shared tutorial panel and existing settings actions."""

from dataclasses import dataclass, replace

from red_handed.ui.tutorial_controller import TutorialContext, TutorialStep


@dataclass(frozen=True)
class CustomisationContext(TutorialContext):
    timing_open: bool = False
    timing_dirty: bool = False
    timing_error: str = ""
    activation_delay: float = 3.0
    recovery_delay: float = 5.0
    applications_open: bool = False
    applications_dirty: bool = False
    applications_error: str = ""
    applications_enabled: bool = False
    applications_count: int = 0
    saved_applications_enabled: bool = False
    saved_applications_count: int = 0


STEPS = {
    "timing": (
        TutorialStep("Open timing settings", "Click Detection & Timing in the sidebar.", "timing"),
        TutorialStep("Wait before covering", "Set the cover delay: how long another person must remain in the zone "
                     "before protection activates (0-10 seconds). Choose Next to review restoration.", "activation", True),
        TutorialStep("Wait before restoring", "Set the restore delay: how long the zone must remain clear before "
                     "automatic protection clears (0-10 seconds). Manual protection is independent.", "recovery", True),
        TutorialStep("Save timing", "Click Save Settings. Sensitivity is unavailable because it currently has no effect.", "save_timing"),
        TutorialStep("Timing saved", "", None, True, "Finish"),
    ),
    "shortcut": (
        TutorialStep("Open shortcut settings", "Click Protection Mode in the sidebar.", "protection_mode"),
        TutorialStep("Set your emergency shortcut", "Enter a shortcut, then click Save Protection Settings. "
                     "Use Ctrl, Alt or Shift with a letter, number or F1-F11. Conflicts keep your previous shortcut.", "hotkey"),
        TutorialStep("Try your shortcut (optional)", "", "home", True, "Skip test"),
        TutorialStep("Shortcut guide complete", "", None, True, "Finish"),
    ),
    "applications": (
        TutorialStep("Open protected applications", "Click Protected Applications in the sidebar.", "applications"),
        TutorialStep("Choose when to protect", "Enable the application restriction to protect only while a listed app "
                     "is in front. Leave it off to monitor all apps. Manual protection works either way.", "enable_applications", True),
        TutorialStep("Choose applications", "Click Add executable... and select an installed app's .exe file. "
                     "An enabled empty list blocks automatic protection. Existing entries can be kept.", "add_application"),
        TutorialStep("Save application settings", "Click Save Application Settings. This restricts when the entire "
                     "primary display is covered; it does not cover individual app windows.", "save_applications"),
        TutorialStep("Application settings saved", "", None, True, "Finish"),
    ),
}


class CustomisationController:
    def __init__(self, show_step, hide):
        self._show_step, self._hide = show_step, hide
        self.mode = "timing"
        self.index = None
        self.context = CustomisationContext()
        self._last_render = None
        self._reviewing = False
        self._reset_test()

    @property
    def active(self):
        return self.index is not None

    def start(self, mode, context):
        if mode not in STEPS:
            raise ValueError("Unknown customisation guide.")
        self.mode, self.index, self.context = mode, 0, context
        self._last_render = None
        self._reviewing = False
        self._reset_test()
        self.update(context)

    def update(self, context):
        self.context = context
        if not self.active:
            return
        panel_open = {"timing": context.timing_open, "shortcut": context.protection_open,
                      "applications": context.applications_open}[self.mode]
        dirty = {"timing": context.timing_dirty, "shortcut": context.protection_dirty,
                 "applications": context.applications_dirty}[self.mode]
        editing = self.index not in (0, len(STEPS[self.mode]) - 1)
        if self.mode == "shortcut" and self.index == 2:
            editing = False  # The optional test is on Home, not in the editor.
            if self._test_started and context.test_requested:
                self._test_failed = bool(context.protection_error or not context.protection_active)
                self._test_observed |= context.protection_active and bool(context.actual_mode)
            elif self._test_started and (context.automatic_requested or context.manual_requested):
                self._test_failed = True
        if dirty and self.index == len(STEPS[self.mode]) - 1:
            self.index = 1 if self.mode == "shortcut" else 3
        if self.mode == "shortcut" and self.index == 2 and dirty:
            self.index = 1
            self._reset_test()
        if editing and not panel_open:
            self.index = 0
            self._reviewing = False
        if not self._reviewing and self.index == 0 and panel_open:
            self.index = 1
        if self.mode == "applications" and self.index == 3 and context.applications_enabled and not context.applications_count:
            self.index = 2
        self._render()

    def next(self):
        if not self.active or not self._step().next_enabled:
            return
        if self.index == len(STEPS[self.mode]) - 1:
            self.skip()
            return
        self.index = 3 if self.mode == "applications" and self.index == 1 and not self.context.applications_enabled else self.index + 1
        self._reviewing = False
        self.update(self.context)

    def back(self):
        if self.active and self.index > 0 and not self._test_started:
            self.index = 1 if self.mode == "applications" and self.index == 3 and not self.context.applications_enabled else self.index - 1
            self._reviewing = True
            self._render()

    def saved(self, mode, context):
        if self.active and self.mode == mode and self.index > 0:
            if mode == "applications" and context.saved_applications_enabled and not context.saved_applications_count:
                self.index = 2
            else:
                self.index = 2 if mode == "shortcut" else 4
            self._reviewing = False
        self.update(context)

    def application_added(self, context):
        if self.active and self.mode == "applications" and self.index == 2 and context.applications_enabled:
            self.index = 3
        self.update(context)

    def test_started(self, context):
        if self.active and self.mode == "shortcut" and self.index == 2 and context.test_requested:
            self._reset_test()
            self._test_started = True
        self.update(context)

    def shortcut_used(self):
        if self._test_started and self.context.test_requested:
            self._shortcut_seen = True

    def test_finished(self, context):
        if self.active and self.mode == "shortcut" and self.index == 2 and self._test_started:
            self._test_started = False
            if (self._shortcut_seen and self._test_observed and not self._test_failed
                    and not context.protection_error and not context.test_requested
                    and not context.automatic_requested and not context.manual_requested):
                self._verified = True
                self.index = 3
                self._reviewing = False
        self.update(context)

    def _reset_test(self):
        self._test_started = self._test_failed = self._test_observed = False
        self._shortcut_seen = self._verified = False

    def skip(self):
        if self.active:
            self.index = None
            self._last_render = None
            self._hide()

    def _step(self):
        step, context = STEPS[self.mode][self.index], self.context
        if self.mode == "timing":
            if self.index == 3 and context.timing_error:
                return replace(step, instruction="Timing was not saved. Check the error below, correct the values, and retry Save Settings.")
            if self.index == 4:
                return replace(step, instruction=f"Cover after {context.activation_delay:g} seconds of intrusion; "
                               f"restore after {context.recovery_delay:g} seconds clear. Your privacy zone is unchanged.")
        elif self.mode == "applications":
            if self.index == 2:
                return replace(step, next_enabled=bool(context.applications_count), next_label="Keep this list")
            if self.index == 3 and context.applications_error:
                return replace(step, instruction="Application settings were not saved. Check the error below and retry Save Application Settings.")
            if self.index == 4:
                scope = f"restricted to {context.saved_applications_count} listed app(s)" if context.saved_applications_enabled else "not restricted by the app list"
                return replace(step, instruction=f"Automatic protection is {scope}. Manual protection remains independent.")
        elif self.mode == "shortcut":
            if self.index == 1 and context.protection_save_failed:
                return replace(step, target="save_protection", instruction="Shortcut settings were not saved. Check the error below, "
                               "choose an available shortcut, and retry Save Protection Settings.")
            if self.index == 2:
                if context.test_requested:
                    return replace(step, target=None, next_enabled=False, back_enabled=False,
                                   instruction=f"Press {context.hotkey} to dismiss this preview. The guide verifies a shortcut press, "
                                   "not just the five-second timeout.")
                if context.automatic_requested or context.manual_requested:
                    return replace(step, target=None, instruction="Real protection is active. You can skip this optional test "
                                   "without clearing real protection requests.")
                return replace(step, target="test_protection" if context.home_open else "home",
                               instruction=f"Optional: go Home, click Test Protection (5 seconds), then press {context.hotkey} "
                               "to dismiss it. A timeout or Dismiss Test does not verify the shortcut. Or choose Skip test.")
            if self.index == 3:
                result = "Verified during the preview." if self._verified else "The optional shortcut test was skipped."
                return replace(step, instruction=f"Saved shortcut: {context.hotkey}. {result} Automatic protection may remain after manual protection is toggled.")
        return step

    def _render(self):
        rendered = (self._step(), self.index, len(STEPS[self.mode]))
        if rendered != self._last_render:
            self._last_render = rendered
            self._show_step(*rendered)
