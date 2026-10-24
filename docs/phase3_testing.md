# # Phase 3 validation

## Scope

Validate activation and recovery boundaries, including interrupted activation
and re-entry during recovery. Check the asynchronous monitoring pipeline and
correct demonstrated integration defects.

## Environment

- Date:23/10/2026
- Windows version: Windows 11 Home
- Python version: Python 3.13.6
- Camera: USB2.0 HD UVC WebCam

## Findings before changes

The startup function called MainWindow.initialize(), which no longer existed.

The earlier controller tests assumed synchronous detection and used fake
frames without copy(). The Round 3 controller requires copied frames and
collects completed futures on a subsequent frame read.

Several earlier UI tests referenced fields and methods removed in Round 3.

## Automated validation

Unit command:
`.\.venv\Scripts\python.exe -B -m unittest discover -s tests/unit -v`

Actual result: Not run.

Integration command:
`.\.venv\Scripts\python.exe -B -m unittest discover -s tests/integration -v`

Actual result: Tests Pass.

Risk boundary tests use explicit monotonic timestamps without sleeps.
Pipeline tests use controlled futures, fake frames, and a fake clock.
UI persistence tests use temporary files and real Tk widgets.

These checks do not establish physical camera accuracy or native detector
performance.

## Manual checks

| Check | Result | Observations |
|---|---|---|
| Application startup | Tests Pass | |
| Sustained intrusion activates risk | Tests Pass| |
| Interrupted intrusion restarts activation | Tests Pass | |
| Sustained absence clears risk | Tests Pass | |
| Re-entry cancels recovery | Tests Pass | |
| Zero delays | Tests Pass | |
| Settings changes reset timing | Tests Pass | |
| Stop/restart resets timing | Tests Pass | |
| No zone means unavailable risk | Tests Pass | |
| Navigation preserves monitoring | Tests Pass | |
| Invalid delay values rejected | Tests Pass | |
| Settings and zone survive restart | Tests Pass | |
| Camera loss clears previous observation | Tests Pass | |

## Limitations

Sensitivity is selectable and saved, but its behavioural effects are undefined.
Face identity is not established; the largest face is assumed to be primary.
Screen protection belongs to a later round.

The detector runs in a worker, while camera capture still occurs on the UI
thread. A slow camera read can delay the UI, and a hung native detector call
can delay shutdown while the worker is joined.
