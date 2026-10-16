# Red-Handed

Red-Handed is a Windows desktop privacy-protection system intended to reduce shoulder-surfing by detecting additional people within a configured privacy zone and activating a selected screen-protection mode.

**Current status:** Round 1 monitoring integration implemented; validation results are recorded in docs/phase1_testing.md.

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

Round 1 uses synchronous capture and detection, so slow native calls can delay
the interface. Later-round features are not yet connected.

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
