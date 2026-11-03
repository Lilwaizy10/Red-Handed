# TODO [FR3, FR12]: Present camera preview, detected-person status,
# privacy-zone calibration, and protection testing.

import tkinter as tk
from tkinter import ttk

from red_handed.core.system_state import MonitoringStatus, SystemState


def detection_labels(state: SystemState) -> tuple[str, str]:
    """FR2.2 / FR12.3: distinguish measured counts from inactive/error states."""
    if state.monitoring_status is MonitoringStatus.INACTIVE:
        return "--", "Detection inactive"
    if state.detection_error:
        return "--", state.detection_error
    result = state.detection
    if result is None:
        return "--", "Waiting for detection..."
    if result.additional_person_present:
        return str(result.person_count), "Additional person detected"
    if result.person_count == 1:
        return "1", "No additional person detected (primary user only)"
    return "0", "No additional person detected (no persons detected)"


class CalibrationView(ttk.LabelFrame):
    """Zone editing controls sharing the main preview and current person count."""

    def __init__(self, parent: ttk.Frame, people_text: tk.StringVar,
                 save_zone=None, discard=None) -> None:
        super().__init__(parent, text="Privacy Zone Setup", padding=8)
        ttk.Label(self, text="Detected persons:").grid(row=0, column=0, sticky="w")
        ttk.Label(self, textvariable=people_text).grid(row=0, column=1, sticky="w")
        ttk.Label(
            self,
            text="Start monitoring, then drag inside the camera image and click Save Zone.\n"
                 "One saved zone loads automatically; saving a new zone replaces it.\n"
                 "Solid blue = zone used for monitoring. Dashed yellow = unsaved replacement.\n"
                 "Discard Draft removes only the unsaved drawing and keeps your saved zone.",
            wraplength=570,
        ).grid(row=1, column=0, columnspan=2, sticky="w")
        self.save_button = ttk.Button(self, text="Save Zone", command=save_zone)
        self.save_button.grid(row=2, column=0, sticky="w", pady=4)
        ttk.Button(self, text="Discard Draft", command=discard).grid(row=2, column=1, sticky="w")
