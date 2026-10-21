"""Settings panel for detection sensitivity and risk-timing delays.

What this module does
---------------------
SettingsView is a Tkinter panel (a ttk.LabelFrame) that lets the user edit:
  * Sensitivity       - Low / Medium / High (picked from a read-only dropdown)
  * Activation delay  - seconds, 0-10
  * Recovery delay    - seconds, 0-10
and save them to the application's settings store.
"""

from dataclasses import replace
import tkinter as tk
from tkinter import ttk

from red_handed.core.settings import Sensitivity


def _parse_delay(label: str, raw: str) -> float:
    """Convert the text typed in a delay box into a float.

    Only checks if input is a number. It does NOT check the 0-10 range; that is
    the settings model's job.

    `label` is "Activation" or "Recovery" and is used to build a message that
    tells the user which field is wrong.
    """
    try:
        return float(raw)
    except ValueError:
        # `from None` hides Python's raw "could not convert string to float"
        # traceback chain, so only our friendly message is shown to the user.
        raise ValueError(f"{label} delay must be a number.") from None


class SettingsView(ttk.LabelFrame):
    def __init__(self, parent, get_settings, save_settings) -> None:
        super().__init__(parent, text="Detection & Timing", padding=8)

        # Keep the injected callables. The leading underscore marks them as
        # internal; every other method must use these exact names.
        self._get_settings, self._save_settings = get_settings, save_settings

        # Tk variables are two-way bound to the widgets below: what the user
        # types/selects updates the variable, and .set() updates the widget.
        # master=self ties them to this widget's Tk root so they never attach
        # to a stray default root window.
        self.sensitivity = tk.StringVar(master=self)
        self.activation = tk.StringVar(master=self)  # kept as text until saved
        self.recovery = tk.StringVar(master=self)    # kept as text until saved
        self.feedback = tk.StringVar(master=self)    # message shown under the form

        # Row 0: column headings. enumerate gives the grid column for each title.
        for column, title in enumerate(["Sensitivity", "Activation delay (0-10s)", "Recovery delay (0-10s)"]):
            ttk.Label(self, text=title).grid(row=0, column=column, sticky="w", padx=4)

        # Row 1: the three inputs.
        # state="readonly" means the user can only pick from the list, so an
        # invalid sensitivity can't be typed in.
        ttk.Combobox(self, textvariable=self.sensitivity, values=[s.value for s in Sensitivity],
                     state="readonly", width=12).grid(row=1, column=0, padx=4)
        ttk.Entry(self, textvariable=self.activation, width=18).grid(row=1, column=1, padx=4)
        ttk.Entry(self, textvariable=self.recovery, width=18).grid(row=1, column=2, padx=4)

        # Row 2: Save button. Kept as an attribute so other code (or tests)
        # can enable/disable it or invoke it.
        self.save_button = ttk.Button(self, text="Save Settings", command=self.save)
        self.save_button.grid(row=2, column=0, sticky="w", pady=6)

        # Row 3: static note. Sensitivity is stored, but nothing uses it yet,
        # so we tell the user honestly rather than imply it changes behaviour.
        ttk.Label(self, text="Sensitivity is saved; its effect awaits the team's definition.").grid(
            row=3, column=0, columnspan=3, sticky="w")

        # Row 4: dynamic feedback (errors or the success message).
        # wraplength makes long error text wrap instead of widening the panel.
        ttk.Label(self, textvariable=self.feedback, wraplength=570).grid(
            row=4, column=0, columnspan=3, sticky="w")

        # Fill the widgets with the currently stored values. This must come
        # after the variables and widgets exist.
        self.reload()

    def reload(self) -> None:
        """Refresh all inputs from the settings store and clear any message.

        Used at start-up and after a successful save, so the boxes always show
        what is actually stored (for example "5." becomes "5.0").
        """
        settings = self._get_settings()
        self.sensitivity.set(settings.sensitivity.value)  # enum -> its text, e.g. "Medium"
        self.activation.set(str(settings.activation_delay))
        self.recovery.set(str(settings.recovery_delay))
        self.feedback.set("")

    def save(self) -> None:
        """Validate the form and, if valid, persist it. Runs on Save click.

        Flow:
          1. Build a candidate MonitoringSettings from the form values.
             - Sensitivity(...) raises ValueError for a bad value.
             - _parse_delay raises ValueError for non-numeric text.
             - replace() copies the CURRENT settings (so fields this panel
               doesn't edit, like privacy_zone, are preserved) and swaps in
               the new values. It re-runs __post_init__, which enforces the
               0-10 range and raises ValueError if it is violated.
          2. Hand the valid candidate to the store.
          
        MonitoringSettings is frozen (immutable), so a failed save can never
        leave a half-modified settings object behind.
        """
        try:
            candidate = replace(self._get_settings(), sensitivity=Sensitivity(self.sensitivity.get()),
                                activation_delay=_parse_delay("Activation", self.activation.get()),
                                recovery_delay=_parse_delay("Recovery", self.recovery.get()))
            self._save_settings(candidate)
        except (ValueError, OSError) as error:
            # ValueError: invalid input (message comes from this file or settings.py).
            # OSError:    the store could not write (disk, permissions, ...).
            # Nothing was saved, so leave the user's typed text alone so they
            # can fix it, and tell them why.
            # NOTE: if the store can raise other exception types, add them here;
            # otherwise Tk will just print a traceback and the user sees nothing.
            self.feedback.set(f"Not saved: {error}")
            return

        # Success path. Reload first so the boxes show the stored values, then
        # set the message. Order matters: reload() clears the feedback text.
        self.reload()
        self.feedback.set("Settings saved. Risk timing restarts with the next detection.")