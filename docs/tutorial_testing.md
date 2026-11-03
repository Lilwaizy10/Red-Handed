# Guided setup validation and presentation

## Scope and access

The core guide covers camera startup, privacy-zone drawing or reuse, saving,
protection selection, a five-second preview, and a completion summary.
Optional guides cover timing, the emergency shortcut, and selected applications.
These changes reuse the existing dashboard and protection manager.

- **Guide me through setup** is on Home; **Replay tutorial** is in the sidebar.
- **Customise more** is in the sidebar and on the core completion summary.
- Saved configuration persists; guide progress does not persist across restart.
- Skipping does not save drafts, stop monitoring, or clear protection requests.
- The app stores one saved privacy zone and loads it automatically.

## Automated validation record

- Date: 3 November 2026 (Asia/Singapore).
- Branch: `guided-setup-tutorial`.
- Application-code baseline: `64a240c` (optional customisation walkthroughs).
- Execution environment: Windows, Python 3.13.6 in the repository's `.venv`.
- Camera, native hotkey backend, foreground lookup, browser and screen surface
  are mocked in the guide integration checks. Tk widgets and temporary settings
  stores are real. Journey tests dispatch registered Tk timer callbacks without
  waiting five seconds.

| Suite | Actual result for this documentation update |
|---|---|
| Unit | Passed: 50 tests |
| Integration | Passed: 54 tests |

Run from the repository root:

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
.\.venv\Scripts\python.exe -B -m unittest discover -s tests/unit -v
.\.venv\Scripts\python.exe -B -m unittest discover -s tests/integration -v
```

In the restricted Codex workspace, validation used an ignored workspace folder
for temporary files to avoid managed temporary-directory permission problems.
If needed, set this before the commands above in the same PowerShell session:

```powershell
New-Item -ItemType Directory -Force -Path .pytest_cache/tutorial-checks | Out-Null
$env:TEMP = (Resolve-Path .pytest_cache/tutorial-checks).Path
$env:TMP = $env:TEMP
```

These environment overrides apply only to the current shell process and its
children. Open a fresh shell to use the normal temporary-directory settings.

The relevant tests are:

- `tests/unit/test_tutorial_controller.py`: core guide transitions and gating.
- `tests/unit/test_customisation_controller.py`: optional guide transitions.
- `tests/integration/test_tutorial_ui.py`: real widget wiring, failures, layout,
  save behaviour, preview interruption and fallback reporting.
- `tests/integration/test_tutorial_journey.py`: connected fresh and saved setup,
  restart, failure recovery, real shortcut-manager dispatch with a fake backend,
  skip/replay, registered timeouts, optional guides and cleanup.

## Desktop rehearsal checklist

Minimum-size layouts were visually checked with mocked data during development.
Automated layout checks cover control visibility, resize tracking and highlights
that leave the target clickable. Those results do not validate a physical camera,
native global shortcut registration, Chrome startup, or real display coverage.

The live checks below have **not been run for this documentation update**. Mark
each result after rehearsing on the presentation computer; include any failure
and its recovery action in Notes.

| Check | Expected result | Result / Notes |
|---|---|---|
| First impression | Home explains the privacy benefit and exposes the guide and preview. | Not run live |
| Camera startup | Start opens a live preview; the guide waits for an image. | Not run live |
| Camera failure | Retry guidance appears; Next cannot bypass the missing preview. | Not run live |
| Draw zone | Dragging inside the image creates a dashed yellow draft; a plain click does not. | Not run live |
| Save and reload | Save produces the solid blue zone; restart loads it automatically. | Not run live |
| Existing zone | Keep uses the loaded zone; replacement affects monitoring only after Save Zone. | Not run live |
| Draft and form edits | Back/Skip keep inputs; guarded navigation requires Save or Discard. | Not run live |
| Protection settings | Each mode is explained; a conflicting shortcut or failed save preserves the prior configuration. | Not run live |
| Overlay and blackout | Test is visibly labelled, covers the primary display, and ends after five seconds or dismissal. | Not run live |
| Decoy mode | Chrome opens when available; otherwise the overlay and status identify the fallback. | Not run live |
| Real protection during test | An existing request blocks testing; a new real request survives the test timeout. | Not run live |
| Completion summary | Saved zone, mode, shortcut, actual preview result and current status are accurate. | Not run live |
| Timing guide | Invalid delays stay unsaved; valid values save; sensitivity is unavailable. | Not run live |
| Shortcut guide | Pressing the registered shortcut during a preview verifies it; timeout or Dismiss Test alone does not. | Not run live |
| Applications guide | Cancelling the picker does not advance; enabled empty lists are explained; saving applies the restriction. | Not run live |
| Keyboard navigation | Tab / Shift+Tab reach guide and settings controls; Enter/Space activate focused controls; focus remains visible. | Not run live |
| Resize | At 940 x 800 and larger, guide controls and Save buttons remain visible, and highlights follow controls. | Not run live |
| Exit during preview | Closing releases camera, shortcut and protection resources without a later callback error. | Not run live |

Zone drawing currently requires a pointer drag. The keyboard check does not
establish that drawing a zone is keyboard-accessible or that the app meets a
particular accessibility standard.

## Presentation preparation

1. Launch with `.\.venv\Scripts\python.exe run_red_handed.py`. Confirm camera
   access and rehearse the guide on the computer you will present from.
2. For the opening preview, save **Privacy Overlay**, return Home, and start
   with monitoring stopped and no manual or test request active. The test button
   is disabled while real protection is requested.
3. Keep the saved zone if it suits the room. Rehearse **Replay tutorial** using
   **Keep this zone**; use **Draw a replacement** when demonstrating calibration.
4. Check the configured shortcut and which display is primary. Protection covers
   the primary display; it is not a Windows lock screen or secure desktop.
5. If demonstrating automatic detection, arrange for a second person to enter
   the saved zone while you remain nearest the camera. The largest detected face
   is treated as the primary user. Hold the additional face in the zone for the
   configured cover delay, then leave it clear for the configured restore delay.
   If the selected-application restriction is enabled, put a listed application
   in the foreground before this demonstration.

## Fifteen-second opening

| Time | Action and suggested words |
|---|---|
| 0-3 seconds | Point to the Home description: “Red-Handed helps protect against shoulder surfers.” |
| 3-5 seconds | Click **Test Protection (5 seconds)**: “Here's the screen cover.” |
| 5-10 seconds | Let the labelled preview finish. Describe this as a preview of protection, not proof of automatic detection. |
| 10-15 seconds | Click **Guide me through setup** or **Replay tutorial**: “This guide walks you through the camera, privacy zone, and protection.” |

The hook is fifteen seconds; completing setup takes longer. Continue with one
customer task at a time:

1. Follow Start Monitoring and wait for the live image.
2. Show the blue saved zone and explain that it is already selected. Keep it,
   or draw and save a replacement to demonstrate the yellow-to-blue change.
3. Choose a protection mode, save or keep its current settings, and run the
   guide's preview again so it can reach its completion summary.
4. Point out the difference between configured settings, the actual preview
   mode and current protection status. Finish the guide.
5. If time permits, open **Customise more** and demonstrate just one optional
   guide relevant to the customer's question.

If camera access fails, demonstrate the recovery guidance and the independent
protection preview, and state that live automatic detection is unavailable in
that run. If Chrome is unavailable, identify the overlay fallback shown by the
app. Use the actual status and the recorded live-check results when answering
questions about what was demonstrated.
