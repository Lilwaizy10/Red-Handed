# Red-Handed

Red-Handed is a Windows desktop privacy-protection system intended to reduce shoulder-surfing by detecting additional people within a configured privacy zone and activating a selected screen-protection mode.

**Current status:** Phase 6 handoff. See the [final report](docs/final_report.md) for validation results and open checks, and the
[traceability matrix](docs/traceability.md) for requirements and evidence.

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

Run the unit and integration checks from the repository root:

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
.\.venv\Scripts\python.exe -B -m unittest discover -s tests/unit -v
.\.venv\Scripts\python.exe -B -m unittest discover -s tests/integration -v
```
After installing the dependencies, you can also double-click
`launch_red_handed.bat`. The launcher uses `.venv\Scripts\python.exe` and
shows a message if the virtual environment is missing.

For a walkthrough, use the [demo checklist](docs/demo_checklist.md).
The synthetic demo exercises the interface and protection flow. It does not
measure live face detection accuracy.

## Guided setup

On Home, click **Guide me through setup**, or choose **Replay tutorial** in the
sidebar. The guide highlights the control to use and waits for the relevant
action to succeed:

1. Click **Start Monitoring** and wait for the live preview. If the camera is
   unavailable, follow **Retry Camera Access**.
2. Open **Privacy Zone Setup**. Drag inside the camera image, then click
   **Save Zone**. If a saved zone exists, choose **Keep this zone** or
   **Draw a replacement**.
3. Open **Protection Mode**. Choose a mode and save, or choose
   **Keep current settings**.
4. Return Home and click **Test Protection (5 seconds)**. The preview ends after
   five seconds or can be dismissed early with **Dismiss Test** or the configured
   shortcut. It does not start monitoring.
5. Review the saved settings, actual preview mode, and current runtime status.
   Choose **Finish** or **Customise more**.

The sidebar's **Customise more** menu also provides independent optional guides:

- **Timing:** set the wait before covering and restoring the screen, then save.
- **Emergency shortcut:** save a shortcut and optionally verify it by pressing it
  during a protection preview. A timeout alone does not verify the shortcut.
- **Selected applications:** choose whether to restrict automatic protection,
  select installed `.exe` files, and save. An enabled empty list blocks automatic
  protection; manual protection remains independent.

Guide progress is kept in memory. Saved settings survive restart, while replay
checks the current setup again. **Skip tutorial** leaves monitoring, protection
requests, and unsaved inputs in place. During a guide, navigation that would
discard edits asks you to save or use **Discard changes** / **Discard Draft**.

## Privacy zone and detection

There is one saved zone. It loads automatically; no further selection is needed.
The solid blue outline is the zone used for monitoring. A dashed yellow outline
is an unsaved replacement. **Save Zone** replaces the saved zone; **Discard Draft**
keeps it. With a live preview, Home shows the saved outline as read-only.
Drawing is available in **Privacy Zone Setup** while a camera image is displayed.

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
unavailable risk. Sensitivity has no defined behavioural effect, so its control
is disabled and labelled unavailable; the stored value is preserved.

## Screen protection

Open Protection Mode to choose Privacy Overlay, Screen Blackout, or Decoy Website
and configure the emergency shortcut. The default shortcut is Ctrl+Alt+P.

Decoy Website requires Google Chrome and Selenium from requirements.txt.
Browser operations run in a background worker. Privacy Overlay covers the
primary display while the decoy starts or is unavailable; the dashboard shows
the actual active mode. Closing the decoy restores the overlay on the next
poll and triggers a browser retry. The decoy is a maximized ordinary browser
window, so it does not provide the overlay's topmost/full-display coverage.
Application-aware protection retains the preceding application's eligibility
while Chrome starts and while the decoy has focus.

Emergency Protect and the shortcut toggle manual protection, including when
monitoring is stopped or camera access is unavailable.

Automatic protection follows confirmed privacy risk and remains active during
pending recovery. Automatic and manual requests are independent. Stop Monitoring
clears only the automatic request.

Home and Privacy Zone Setup provide a labelled five-second Test Protection
action. An existing automatic or manual request prevents starting a test.
A real request arising during a test is not cleared by its timeout. The guide
reports a failed or interrupted preview without marking that step complete.

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

## Privacy and limitations

The app processes camera frames locally. Its history stores event metadata,
not webcam images or video. Settings and history are stored in
`%LOCALAPPDATA%\Red-Handed` by default.

MediaPipe Tasks can send performance and usage telemetry. Local camera
processing does not mean that the app and its dependencies make no network
requests. Decoy Website uses a local page, but Chrome or Selenium driver
setup may require network access.

The app assumes the largest detected face is the primary user. It does not
identify people. Sensitivity is disabled because the team has not defined
how it should affect detection. Protection covers the primary display and
is not a Windows lock screen. Decoy Website uses a maximized browser;
Privacy Overlay is used while the decoy starts or is unavailable.

## Folder structure

```text
docs/                   SC2006 laboratory documentation
src/red_handed/         Python application package
  core/                 Monitoring, risk, protection, and runtime state
  detection/            Camera, person detection, and privacy-zone concerns
  ui/                   User-interface views and controls
  storage/              Settings and metadata-only event persistence
  system/               Windows hotkey and active-application integration
tests/                   Unit and integration test suites
```

Future enhancements FUT1–FUT8 are currently out of scope.
