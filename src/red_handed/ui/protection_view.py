"""Protection settings panel for the Red Handed app.

This file defines ProtectionView, a small Tkinter panel that lets the user:
  1. pick a protection mode (one radio button per ProtectionMode member), and
  2. type an emergency hotkey that triggers the manual protection request.

"""

import tkinter as tk
from tkinter import ttk

from red_handed.core.settings import ProtectionMode, ProtectionSettings


# Spacing / sizing constants, kept in one place so they are easy to tweak.
WRAP_PADDING = 30      # pixels subtracted from the frame width when wrapping text
MIN_WRAP = 200         # never wrap text narrower than this, even in a tiny window


class ProtectionView(ttk.LabelFrame):
    """A framed panel for choosing the protection mode and emergency hotkey."""

    def __init__(self, parent, get_settings, save_settings):
        """
        parent        - the Tk widget that will contain this panel
        get_settings  - callable returning the current ProtectionSettings
        save_settings - callable that takes a ProtectionSettings and persists
                        it (it should raise ValueError/OSError on failure)
        """
        super().__init__(parent, text='Protection Mode & Emergency Hotkey', padding=8)

        # Store the injected callbacks so reload() and save() can use them.
        self._get_settings = get_settings
        self._save_settings = save_settings

        # Tk variables hold the live values of the widgets. Passing master=self
        # ties them to this frame's Tk root, which avoids "no default root" errors.
        self.mode = tk.StringVar(master=self)      # selected radio button value
        self.hotkey = tk.StringVar(master=self)    # text typed in the hotkey box
        self.feedback = tk.StringVar(master=self)  # success / error message line

        # Layout 
        # Let column 0 stretch when the window is resized so text can reflow.
        self.columnconfigure(0, weight=1)

        # One radio button per protection mode. Rows 0..N-1 are used.
        modes = list(ProtectionMode)
        for row, mode in enumerate(modes):
            if mode is ProtectionMode.DECOY_WEBSITE:
                ttk.Radiobutton(
                    self,
                    text=mode.value + " (Requires Google Chrome)",
                    value=mode.value,
                    variable=self.mode,
                ).grid(row=row, column=0, sticky='w')
            else:
                ttk.Radiobutton(
                    self,
                    text=mode.value,
                    value=mode.value,
                    variable=self.mode,
                ).grid(row=row, column=0, sticky='w')

        # Everything below is positioned relative to 'base' (the number of
        # modes), so adding a new ProtectionMode never causes widgets to
        # overlap. Previously these row numbers were hard-coded.
        base = len(modes)

        #Hotkey
        ttk.Label(
            self, text='Emergency hotkey (Ctrl/Alt/Shift + A-Z, 0-9, F1-F11):'
        ).grid(row=base, column=0, sticky='w')

        ttk.Entry(self, textvariable=self.hotkey, width=28).grid(
            row=base+1, column=0, sticky='w'
        )

        ttk.Button(
            self, text='Save Protection Settings', command=self.save
        ).grid(row=0, column=1, padx=8)

        # Static note explaining the current limitations to the user.
        self._note_label = ttk.Label(
            self,
            text='The shortcut toggles the manual request only. Automatic protection may remain.\n'
                 'Only the primary display is covered. Use Protected Applications to limit when automatic protection runs.',
            wraplength=650,
        )
        self._note_label.grid(row=base+2, column=0, columnspan=2, sticky='w')

        # Status line: shows "saved" or "not saved: <reason>".
        self._feedback_label = ttk.Label(self, textvariable=self.feedback, wraplength=650)
        self._feedback_label.grid(row=base+3, column=0, columnspan=2, sticky='w')

        # Re-wrap the two long labels whenever the panel changes width.
        self.bind('<Configure>', self._on_resize)

        # Fill the widgets with the currently saved settings.
        self.reload()

    def _on_resize(self, event):
        """Keep long text wrapped to the panel width instead of a fixed 650px."""
        wrap = max(event.width - WRAP_PADDING, MIN_WRAP)
        self._note_label.configure(wraplength=wrap)
        self._feedback_label.configure(wraplength=wrap)

    def reload(self): 
        """Load saved settings into the widgets, discarding unsaved edits.

        Errors are shown in the feedback line rather than raised, so a missing
        or corrupt settings file cannot stop the whole view from being built.
        """
        try:
            settings = self._get_settings()
        except (ValueError, OSError) as error:
            self.feedback.set(f'Could not load settings: {error}')
            return

        self.mode.set(settings.mode.value)
        self.hotkey.set(settings.hotkey)
        self.feedback.set('')  # clear any old message

    def save(self):
        """Validate and persist the settings currently shown in the widgets."""
        # Guard: mode can be empty if loading failed and the user never picked one.
        # Without this, ProtectionMode('') raises an unfriendly error message.
        if not self.mode.get():
            self.feedback.set('Not saved: please select a protection mode.')
            return

        # strip() removes accidental leading/trailing spaces from the hotkey.
        hotkey = self.hotkey.get().strip()

        try:
            # ProtectionMode(...) turns the radio value back into an enum member
            # (raises ValueError if it is invalid). The save callback is expected
            # to validate the hotkey and raise ValueError/OSError on problems.
            self._save_settings(ProtectionSettings(ProtectionMode(self.mode.get()), hotkey))
        except (ValueError, OSError) as error:
            self.feedback.set(f'Not saved: {error}')
        else:
            # Runs only if no exception was raised above.
            self.hotkey.set(hotkey)  # show the cleaned-up value back to the user
            self.feedback.set('Protection mode and hotkey saved.')
