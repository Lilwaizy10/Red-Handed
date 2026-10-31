# Red-Handed

Red-Handed is a Windows desktop privacy-protection system intended to reduce shoulder-surfing by detecting additional people within a configured privacy zone and activating a selected screen-protection mode.

**Current status:** Phase 5 application/history integration implemented; validation results are recorded in docs/phase5_testing.md.

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

Face detection runs through one background worker with no frame backlog.
Camera capture remains on the UI thread. Results from previous monitoring
sessions or settings configurations are discarded.

Continuous intrusion activates privacy risk after the configured activation
delay. Continuous absence clears it after the recovery delay. Re-entry cancels
recovery, and pending recovery still counts as active risk.

Unknown or stale evidence resets transient timing and is displayed as
unavailable risk. Sensitivity is saved but has no defined behavioural effect.

## Screen protection

Open Protection Mode to choose Privacy Overlay or Screen Blackout and configure
the emergency shortcut. The default shortcut is Ctrl+Alt+P.

Emergency Protect and the shortcut toggle manual protection, including when
monitoring is stopped or camera access is unavailable.

Automatic protection follows confirmed privacy risk and remains active during
pending recovery. Automatic and manual requests are independent. Stop Monitoring
clears only the automatic request.

Status / Calibration includes a labelled five-second Test Protection action.
A real automatic request is not cleared by the test timeout.

Protection covers the primary display only. It is not a Windows lock screen
or secure desktop. 

## Protected applications and event history

Protected Applications controls whether automatic protection requires a matching
foreground executable. Matching uses normalized full paths. An enabled empty
list or unknown foreground blocks automatic protection. Manual protection
remains independent.

Event History displays local timestamps and privacy-event transitions.
History is stored beside settings in events.json and survives restart.
Clear History requires confirmation and persists across restart.

History stores event metadata only. Recording errors are displayed in the
history panel and do not disable screen protection.

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
