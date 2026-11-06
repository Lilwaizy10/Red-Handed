# Red-Handed Phase 6 final handoff

Phase 6 automated validation passed: 50 unit tests and 56 integration tests,
including both controlled acceptance scenarios. Physical desktop acceptance
remains open where observations are incomplete or measurements are missing.

## Release under review

- Tested revision: `6fa15ab10742e9210d13b3be7378e3e31147c387` on `final-checks`.
  The working tree was clean before verification. Application code at this
  revision matches the Phase 6 acceptance merge `2434d92`.
- Verification date: 6 November 2026 (Singapore time).
- Environment: Windows 11 Home 25H2, build `26200.9711`; Python `3.13.6`.
- Installed dependencies: MediaPipe `1.0.1`, OpenCV contrib `4.14.0.94`,
  Pillow `12.3.0`, Selenium `4.52.0`.
- Physical camera and display configuration: not exercised in this run.

## Delivered features

Red-Handed provides guided setup, camera monitoring and face counting, a saved
privacy zone, timed automatic protection, manual emergency protection, optional
application-aware gating, and persistent event history. The protection modes
are Privacy Overlay, Screen Blackout, and Decoy Website with overlay fallback.
Phase 6 adds a Windows launcher and improves restart, persistence, and cleanup
handling.

Use the [README](../README.md) for setup and operation, the [traceability
matrix](traceability.md) for requirements and evidence, and the [demo
checklist](demo_checklist.md) for rehearsal. Keep the normal user settings and
history separate from disposable validation data.

## Verification results

| Check | Evidence from this run | Result |
|---|---|---|
| Dependency consistency | `python -m pip check` in the project virtual environment | Passed: no broken requirements |
| Unit suite | `unittest discover -s tests/unit` | Passed: 50 tests |
| Integration suite | `unittest discover -s tests/integration -v` | Passed: 56 tests in 32.230 s |
| S1: startup, zone, risk, protection and recovery | `test_startup_zone_risk_protection_recovery_journey`, included in the integration total | Passed with controlled inputs |
| S2: camera failure and manual protection | `test_camera_failure_keeps_manual_protection_usable_until_recovery`, included in the integration total | Passed with controlled inputs |
| Persistence and confirmed Clear | Automated settings reload, event reload and Clear checks in the two suites | Passed with disposable storage |
| Launcher without its virtual environment | Ran a copy of `launch_red_handed.bat` in a disposable folder without `.venv` | Passed: showed the expected message and exited with code 1 |
| Bundled model and detector cleanup | `tests/manual/phase5_5_benchmark.py --seconds 2`, using synthetic pixels and the actual MediaPipe model | Passed: 20 updates in 2.002 s (9.99/s), zero faces, no detection error; synthetic camera released, worker joined, detector closed |
| Normal launcher, desktop rehearsal and physical exit/restart | Real camera, display, shortcut, and Chrome operation | Not rerun in this verification |

The two acceptance scenarios exercise the application with controlled camera,
detector, display surface and hotkey components. The short model check used a
blank synthetic input after warm-up. Neither establishes live detection accuracy,
webcam throughput, physical shortcut latency or visible protection coverage.

To reproduce the automated checks from the repository root:

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
.\.venv\Scripts\python.exe -B -m pip check
.\.venv\Scripts\python.exe -B -m unittest discover -s tests/unit -v
.\.venv\Scripts\python.exe -B -m unittest discover -s tests/integration -v
.\.venv\Scripts\python.exe -B tests/manual/phase5_5_benchmark.py --seconds 2
```

The first suite attempts did not finish using the default temporary directory
in the restricted verification shell. Both suites completed with `TEMP` and
`TMP` directed to a writable location. A 20-second cap also interrupted an
integration attempt; the completed run used a 90-second cap.

## Earlier acceptance evidence and open checks

The [manual acceptance checklist](manual_acceptance_checklist.md) records
Ahmad's 5 November run as 50 unit tests, 56 integration tests, and two focused
acceptance tests passed. Its tested revision is blank and it does not identify
the normal app or synthetic harness for each observation. The automated results
above independently verify the current revision; they do not resolve these
desktop observations:

| Open item | Evidence needed |
|---|---|
| S1 entry and activation | The two actual results say **Pending recovery** where **Pending activation** and **ACTIVE** were expected. Confirm or rerun both steps and record the observed state and display behavior. |
| S2 manual protection after camera loss | The **Manual protection on** row has no actual observation. Record whether the display was covered with the camera unavailable. |
| Native launcher, display and exit | Run the normal launcher and check physical coverage, global key delivery, and release of the camera, surface and shortcut after exit. Record the build, display and camera. |
| Quantitative and broader acceptance | Record controlled detection and false-activation counts; native throughput and visible timing measurements; a two-hour endurance run; first-time usability; and offline and Windows/camera compatibility results. Checked boxes alone do not establish these targets. |

## Privacy and limitations

Camera frames are processed locally. Settings and allowlisted event metadata
are stored in `%LOCALAPPDATA%\Red-Handed` by default; history contains no camera
images or video. MediaPipe Tasks can send performance and usage telemetry.
Decoy Website uses a local page, but Chrome or Selenium driver setup may require
network access. No network-traffic audit was performed.

The largest detected face is assumed to be the primary user; the detector does
not identify people. Sensitivity (FR9.4) is partial: the saved value is preserved,
but the control is disabled because its effect is undefined. Overlay and blackout
cover the primary display. The decoy is an ordinary maximized browser, with an
overlay while it starts or is unavailable. These modes do not lock Windows.
