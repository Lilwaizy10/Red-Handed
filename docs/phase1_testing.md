# Phase 1 testing

## Scope

Connect the existing camera manager, face detector, and dashboard.
Implement Start, Stop, camera retry, live preview, face-count updates,
and resource cleanup.

## Environment

- Test date: 16/10/2026
- Windows version: Windows 11 Home
- Python version: Python 3.13.6
- Camera: USB2.0 HD UVC WebCam
- Dependency versions:
Name: opencv-contrib-python
Version: 4.14.0.94
Name: mediapipe
Version: 1.0.1
Name: pillow
Version: 12.3.0

## Automated tests

Command:

`.\.venv\Scripts\python.exe -B -m unittest discover -s tests/unit -v`

Result: Tests pass

The controller tests use mocked camera and detector dependencies.
They verify lifecycle and error handling, not physical camera operation
or real face-detection accuracy.

## Manual checks

| Check | Result | Observations |
|---|---|---|
| Dashboard startup | Test pass | |
| Start and live preview | Test pass | |
| One-face, two-face, and empty-scene counts | Test pass | |
| Stop clears preview and releases camera | Test pass | |
| Five Start/Stop cycles | Test pass | |
| Close while monitoring | Test pass | |
| Startup without camera access | Test pass | |
| Retry after restoring camera access | Test pass | |
| Camera loss during monitoring | Test pass | |

## Limitations

- Capture and detection run synchronously in Phase 1.
- Slow native calls can temporarily delay the interface.
- Face counts do not establish identity or guarantee that nobody is present.
- Privacy zones, risk timing, screen protection and event history belong
  to later rounds.
- No camera frames are intentionally saved by this integration.

