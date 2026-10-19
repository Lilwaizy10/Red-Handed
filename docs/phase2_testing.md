# Phase 2 validation

## Scope

Connect saved privacy-zone settings to monitoring and the calibration UI.
Display whether an additional face centre is inside the saved zone.

## Environment

- Date:20/10/2026
- Windows version: Windows 11 Home
- Python version: Python 3.13.6
- Camera: USB2.0 HD UVC WebCam
- Branch: codex/zone-integration

## Automated tests

Unit command:
`.\.venv\Scripts\python.exe -B -m unittest discover -s tests/unit -v`

Result: All tests ok

Integration command:
`.\.venv\Scripts\python.exe -B -m unittest discover -s tests/integration -v`

Result: All tests ok

Automated tests use mocked detection and camera dependencies.
UI persistence tests use temporary settings files and real Tk widgets.

## Manual checks

| Check | Result | Notes |
|---|---|---|
| No saved zone displays Unconfigured | test ok | |
| Unsaved draft does not affect monitoring | test ok | |
| Save applies the drawn zone | test ok | |
| Saved zone survives restart | test ok | |
| Additional face moves inside/outside | test ok | |
| Primary face is excluded | test ok | |
| Discard preserves saved zone | test ok | |
| Leaving calibration discards draft | test ok | |
| Resizing preserves zone alignment | test ok | |
| Stop/restart clears old membership | test ok | |
| Round 1 controls and cleanup still work | test ok | |

## Behaviour and limitations

Only a successfully saved zone affects monitoring.
Changing the zone preserves sensitivity and activation/recovery settings.
A failed save leaves the previous zone active and retains the draft.

The largest face is assumed to be the primary user.
Other faces count as inside when their centres lie within the saved rectangle,
including its boundary. This does not identify people.

Detection failure produces an unknown result.
A successful observation with no additional face inside produces False.
No saved zone is displayed as Unconfigured.

Risk timing, sensitivity effects, and screen protection are not implemented
by this round. Capture and detection remain synchronous.
