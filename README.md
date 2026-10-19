# Red-Handed

Red-Handed is a Windows desktop privacy-protection system intended to reduce shoulder-surfing by detecting additional people within a configured privacy zone and activating a selected screen-protection mode.

**Current status:** Round 2 privacy-zone integration implemented; validation results are recorded in docs/phase2_testing.md.

**Initial target:** 64-bit Windows 10 and Windows 11

The application connects the camera manager, local face detector, and Tkinter
dashboard. It supports Start/Stop monitoring, live preview, detected-face counts,
camera retry, and cleanup on exit.

From the repository root, create a virtual environment if one does not exist:

```powershell
py -3 -m venv .venv
```

Install dependencies and run:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run_red_handed.py
```

Run controller tests:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests/unit -v
```

The calibration screen supports drawing, saving, and reloading a privacy zone.
Only the saved zone affects monitoring. An additional face is inside when its
centre falls within the zone, including the boundary. The largest detected
face is assumed to be the primary user.

Settings are stored at `%LOCALAPPDATA%\Red-Handed\settings.json`.
Saving a new zone preserves sensitivity and timing settings.

Capture and detection remain synchronous, so slow native calls can delay the
interface. Risk timing and screen protection belong to later rounds.

## Folder structure

```text
docs/                   SC2006 laboratory documentation
src/red_handed/         Provisional Python application package
  core/                 Monitoring, risk, protection, and runtime state
  detection/            Camera, person detection, and privacy-zone concerns
  ui/                   User-interface views and controls
  storage/              Settings and metadata-only event persistence
  system/               Windows hotkey and active-application integration
tests/                   Unit and integration test suites
```

Future enhancements FUT1–FUT8 are currently out of scope.
