# Round 4 Member 5 validation

## Scope

Connect risk evaluation, protection arbitration, display surfaces, global
hotkeys, protection settings, and application cleanup.

## Environment

- Date:27/10/2026
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

Actual result: All tests pass.

Protection integration tests use fake display surfaces, fake hotkey
registration, controlled scheduling, and temporary settings files.
They do not verify physical display coverage or Windows shortcut delivery.

## Manual checks

| Check | Result | Notes |
|---|---|---|
| Manual button with monitoring stopped | passed | |
| Global shortcut while another app has focus | passed | |
| Manual protection without camera access | passed | |
| Privacy Overlay test | passed | |
| Screen Blackout test | passed | |
| Five-second test expiry | passed | |
| Early test dismissal | passed | |
| Automatic risk activation | passed | |
| Recovery restores the display | passed | |
| Automatic/manual overlap | passed | |
| Stop clears only automatic protection | passed | |
| Camera loss retains existing protection | passed | |
| Replacement shortcut | passed | |
| Settings survive restart | passed | |
| Exit while protected and relaunch | passed | |

## Behaviour

Manual protection is independent of monitoring and camera availability.
Automatic and manual requests are independent; either can keep protection on.

Unknown detection or camera evidence does not immediately reveal a display
already protected automatically. Explicit Stop clears the automatic request.

Test Protection ends after five seconds or early dismissal. Ending a test
does not clear real automatic or manual requests.

A conflicting shortcut or failed settings save retains the old binding.
Protection settings are saved alongside existing zone and timing settings.

## Limitations

Only the primary display is covered.
The protection window is not an OS lock or secure desktop.
Application-aware protection and event history belong to Round 5.
A blocked native camera or detector call can delay UI processing or shutdown.

