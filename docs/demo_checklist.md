# Current-scope demonstration checklist

This is a rehearsal plan, not a claim that every step passed. Record actual
results in the manual acceptance checklist. Do not film/save webcam preview;
use synthetic pixels for any submitted demo recording. Explain simulation aloud.

## Setup

- Use 64-bit Windows 10/11 and the README environment/install commands.
- Run the two automated suites first. Close other Red-Handed instances so the
  global shortcut is available. Use a primary display with nonsensitive content.
- Decoy Website additionally needs Google Chrome and the Selenium package from
  requirements.txt. Other protection modes work without them.
- Normal application: `.venv\Scripts\python.exe run_red_handed.py`.
- Deterministic rehearsal: `.venv\Scripts\python.exe -B tests/manual/phase5_desktop.py`.
  This existing harness uses synthetic frames/detections, a saved right-half zone,
  zero delays, temporary metadata files, real Tk surfaces and real Windows
  foreground/hotkey APIs. It is not a detector-quality test or production mode.
  The helper's Python executable path is printed for protected-app selection.
- Do not run the normal application and harness together. Close via Exit or
  Close Red-Handed; the harness also expires after 15 minutes. Its default
  temporary directory is removed on exit. Never pass the normal data directory
  to `--directory`; that option is only for disposable restart demonstrations.

## Flow (operator checklist)

1. Launch; show textual Camera Available / Monitoring Inactive states. Explain
   local camera processing and the MediaPipe performance/utilization telemetry
   disclosure; do not describe the app as network-silent.
2. Start Monitoring. Show preview, count and additional-person status. In the
   synthetic harness the two boxes/count are injected, not inferred by MediaPipe.
3. Open Privacy Zone Setup. Show the saved zone; draw/discard a draft to explain
   that only Save Zone changes active geometry. Keep the right-half saved zone
   for the scripted harness flow, or reset it deliberately before continuing.
4. Select Privacy Overlay. Start the helper's risk pulse: risk begins after five
   seconds and clears 30 seconds after the button press. Observe automatic
   protection then restoration. For nonzero timing, the operator may configure
   documented 0-10 second delays and explain the additional wait.
5. Repeat with Screen Blackout. Show its safe controls; both surfaces are opaque
   and cover the primary display, not a secure desktop or Windows lock.
   Then select Decoy Website and repeat. Privacy Overlay covers the display while
   Chrome starts, then the local decoy page appears. Close Chrome once: the overlay
   returns and the browser retries. The decoy is an ordinary maximized window, so
   it does not provide the overlay's topmost coverage. Return to Privacy Overlay.
6. With the separate focus-target window active, use the configured emergency
   shortcut (default Ctrl+Alt+P), then again to release manual protection.
7. Demonstrate overlap: automatic on, manual on, automatic off -> still covered;
   manual off -> clear. Also test the opposite release order. Stop Monitoring
   clears automatic only; it must not cancel an outstanding manual request.
8. In Protected Applications, add the helper's exact Python executable and enable
   application-aware protection. During risk, switch between that helper and a
   different unprotected app. Unknown foreground or an empty list must block
   automatic only. Manual emergency action must still work. Changing a title
   alone does not change the executable-path match.
9. Open Event History. Show transition rows (not per-frame spam), oldest-first
   ordering, event type and action. Events contain no camera images or boxes.
10. With no protection active, trigger Camera unavailable using the helper (the
    overlay is topmost and would cover the helper panel). Show stopped monitoring,
    the readable error and usable settings/history. Press the emergency shortcut:
    the display is covered with no camera. Press it again to release. Select Camera
    available, Retry if needed, then Start. A new session does not reuse old risk.
    If automatic protection is active when a real camera fails, the display stays
    covered; use the overlay's Stop Monitoring / Clear Automatic button.
11. With a disposable `--directory`, save settings/app list, close, relaunch with
    that same directory, and show persisted settings and event history. Clear
    History only after operator confirmation, restart, and verify it stays empty.
12. Exit while protected/monitoring; confirm the surface and helper disappear and
    the process ends. A normal-camera run must release the webcam indicator too.

## Separate native detector check

`.venv\Scripts\python.exe -B tests/manual/phase5_5_benchmark.py --desktop`
uses synthetic pixels with the actual bundled MediaPipe model, temporary data,
and real UI. It does not supply meaningful faces. `--seconds 10 --camera` is an
opt-in local-webcam aggregate benchmark, not controlled accuracy acceptance.
Never capture a desktop screenshot while real camera preview is visible.

The final SC2006 demo script/video, Lab 4 methodology and human acceptance records
are separate deliverables. FR9.4 sensitivity semantics remain unresolved; don't
demonstrate invented Low/Medium/High behavior or FUT1-FUT8 features.
