# Phase 5 Member 5 validation

## Scope

Integrate application-aware automatic protection, transition recording,
persistent event history, refresh, and confirmed Clear History.

## Environment

- Date:31/10/2026
- Windows version: Windows 11 Home
- Python version: Python 3.13.6
- Camera: USB2.0 HD UVC WebCam
- Branch: codex/protection-integration

## Automated checks

Unit command:
`.\.venv\Scripts\python.exe -B -m unittest discover -s tests/unit -v`

Actual result: Not run.

Integration command:
`.\.venv\Scripts\python.exe -B -m unittest discover -s tests/integration -v`

Actual result: passed.

New checks cover application gating, manual independence, event
deduplication, failed presentation, restart persistence, and confirmation.

## Desktop checks

| Check | Result | Notes |
|---|---|---|
| Protected application during risk | passed | |
| Switch to unprotected application | passed | |
| Switch back during the same risk | passed | |
| Manual protection bypasses gate | passed | |
| Own protection surface does not cause flicker | passed | |
| Disabled application awareness | passed | |
| Enabled awareness with empty list | passed | |
| Transition history | passed | |
| Events survive restart | passed | |
| Cancel Clear preserves history | passed | |
| Confirmed Clear survives restart | passed | |
| Camera-unavailable transition | passed | |

## Behaviour and limitations

Matching uses normalized full Windows executable paths.
Application gating affects automatic protection only.
Unknown foreground applications block automatic protection when awareness
is enabled.

Foreground polling runs every 250 ms. While the protection surface has focus,
the last external application is retained.

History stores validated event metadata and timezone-aware timestamps.
The UI displays local time. Images and video are not recorded in history.

Event writes use the existing background recorder. Storage failures pause
recording and are shown in the history panel.

