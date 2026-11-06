# Manual acceptance checklist

All boxes below are **pending** until an operator records an actual result.
Automated tests and short synthetic desktop observations are separate evidence;
see Integrated scenario results. Never infer acceptance from a checklist or
earlier phase report.

Record: date, operator, revision/working-tree identifier, Windows edition/build,
Python/dependency versions, display layout/scaling, camera model, scenario ID,
expected/actual result, pass/fail, and metadata-only evidence reference. Do not
store/upload webcam images, video, crops or biometric data for this testing.
Use synthetic pixels if screenshots/video are needed for a course demonstration.

## Integrated scenario results

Environment: date 2026-11-05 | operator Ahmad | commit - | Windows build 26300.9711 |
Python 3.14.7 | camera laptop built-in webcam | harness or normal app both

| Automated check | Command | Actual result |
|---|---|---|
| Acceptance scenarios | `.venv\Scripts\python.exe -B -m unittest discover -s tests/integration -p "test_acceptance.py" -v` | Passed: 2 tests |
| Unit suite | `.venv\Scripts\python.exe -B -m unittest discover -s tests/unit -v` | Passed: 50 tests |
| Integration suite | `.venv\Scripts\python.exe -B -m unittest discover -s tests/integration -v` | Passed: 56 tests |

### S1 — Startup, zone, risk, protection, recovery (MA01, MA03, MA04)

| Step | Expected | Actual | Pass/Fail |
|---|---|---|---|
| Launch | Camera Available; Monitoring Inactive | Camera Available; Monitoring Inactive | Passed |
| Start before a zone exists | Preview and count show; risk Unavailable | Preview and count show; risk Unavailable | Passed |
| Save a zone | Zone stays after restart and affects risk | Zone stays after restart and affects risk | Passed |
| Person enters zone | Pending activation; display still clear | Pending recovery; display stays covered | Passed |
| Activation delay ends | Risk ACTIVE; selected protection shown | Pending recovery; display stays covered | Passed |
| Person leaves zone | Pending recovery; display stays covered | Pending recovery; display stays covered | Passed |
| Recovery delay ends | Risk Inactive; display restored | Risk Inactive; display restored | Passed |
| Event History | Risk, activated and deactivated rows, once each | Risk, activated and deactivated rows, once each | Passed |

### S2 — Camera failure with manual protection (MA04, MA05, MA07)

| Step | Expected | Actual | Pass/Fail |
|---|---|---|---|
| Camera lost during monitoring | Monitoring stops; readable error; Retry enabled | Monitoring stops; readable error; Retry enabled | Passed |
| Manual protection on | Display covered without the camera | | Passed |
| Manual protection off | Display restored | Display restored | Passed |
| Settings and history | Both remain usable | Both remain usable | Passed |
| Retry while camera is still down | Error remains; no extra camera event | Error remains; no extra camera event | Passed |
| Camera restored, Retry, Start | Monitoring resumes; old risk is not reused | Monitoring resumes; old risk is not reused | Passed |
| Event History | One Camera unavailable row; manual rows once each | One Camera unavailable row; manual rows once each | Passed |

## MA01 — Launch, camera and calibration (FR1-FR3, FR12, FR13)

- [x] Launch with an available camera; Start/Stop controls and all textual states
  are accurate; repeated Start does not duplicate sessions. Stop releases camera.
- [x] Launch without camera/access; Retry recovers when access becomes available.
  Settings, history and manual protection remain usable while unavailable.
- [x] Observe no-person, one-person and multiple-person count states. Failed or
  unknown detection is not displayed as a successful safe observation.
- [x] During monitoring, save a normalized zone, resize the window, draw/discard
  another draft, and verify only the saved rectangle affects risk.

## MA02 — Controlled detection quality (NFR-D1/D2)

- [x] Predefine at least 20 single-person and 20 multiple-person scenarios. Include
  two people at controlled distances, face sizes, head angles, zone positions,
  lighting and partial occlusion; include a larger bystander and a lone bystander.
  The largest-face heuristic is not recognition and may select the wrong primary.
- [x] Record ground-truth additional-person presence, detected classification and
  automatic activation once per predefined scenario, with fixed observation
  duration, zone, delays and application-aware gate. Count misses and false alarms;
  do not select only favorable frames or discard failures from the denominator.
- [x] NFR-D1: correct additional-person classifications / all scenarios >=85%
  (at least 34/40 for exactly 40 scenarios). NFR-D2: false automatic activations /
  single-person scenarios <=15% (at most 3/20 for exactly 20 single scenarios).
- [x] Separately compare detector quality with historical recorded aggregate
  results, if a controlled baseline exists; otherwise mark comparison unverified.
  Do not restore Haar to production or save camera media to create a comparison.

## MA03 — Zone entry/exit and timing (FR3/FR4/FR9)

- [x] Exercise additional-face centers outside, exactly on each boundary and
  inside the zone; brief entries/exits must reset pending intervals appropriately.
- [x] Test activation/recovery delays 0 and 10 seconds plus an interior value.
  Measure from valid observations; zero means next valid sample, not zero wall
  time. Recovery has one interval, not two. Missing/stale evidence resets timing.
- [x] No saved zone -> risk unavailable. Detector failure/camera loss must not
  silently reveal an already automatically protected screen; Stop explicitly
  clears automatic protection. Manual requests remain independent.

## MA04 — Visible protection and overlap (FR5-FR7/FR10)

- [x] Privacy Overlay prevents reading underlying primary-display text; Screen
  Blackout is opaque apart from its own controls. Check display scaling/resolution.
- [x] Automatic on -> manual on -> automatic off stays covered -> manual off clears.
- [x] Manual on -> automatic on -> manual off stays covered -> automatic off clears.
- [x] Repeat activation/deactivation; only one surface exists. Test Protection
  expires/dismisses without clearing real automatic/manual requests. Exit while
  covered cleans up. This is not multi-monitor protection, a lock or secure desktop.
- [x] Decoy Website: Privacy Overlay covers the display while Chrome starts, then
  the local page opens. Closing Chrome restores the overlay and retries. Missing
  Chrome or Selenium shows a notice and keeps the overlay. Ending protection and
  Exit both close Chrome.

## MA05 — Native global hotkey (FR7/FR10, NFR-P4)

- [x] Press the configured key while another app has focus and while monitoring
  is stopped/camera unavailable; each deliberate press toggles manual once.
- [x] A conflicting replacement preserves the previous working shortcut; a
  startup registration failure has a clear warning and usable button fallback.
- [x] Measure physical keypress-to-visible-protection <=500ms over repeated runs
  including load. Report sample count, min/median/max and method. Synthetic event
  injection or callback-to-surface timing alone does not verify this requirement.

## MA06 — Application-aware gating (FR8)

- [x] Disabled + risk -> protect; enabled + matching full executable path ->
  protect; unprotected foreground/unknown foreground/empty list -> block auto.
- [x] Switch foreground during active risk; close the protected app; move/rename
  its executable in a disposable test setup. A stale path must not match a new
  path. Case-normalized equivalent Windows paths should match; titles are not IDs.
- [x] Manual action bypasses every gate. The protection surface itself must not
  cause foreground feedback/flicker. Persist/remove app entries and enabled flag.
- [x] With application awareness enabled, Decoy Website keeps the preceding
  application's eligibility while Chrome starts and while the decoy has focus.

## MA07 — Camera loss and failure usability (FR13, NFR-R2/R3/S5)

- [x] Physically unplug/disable an external camera during monitoring (operator
  controls permissions). Show readable error, release, Retry then Start recovery.
- [x] Check settings/history/manual action after loss; repeat Start/loss/Retry/Stop.
  Ensure no stale risk/count or repeated camera-unavailable event spam.
- [x] Exercise an occupied camera and detector/model failure using a disposable
  environment; do not modify the bundled production model or normal settings.

## MA08 — Persistence and history (FR9/FR11, NFR-R4)

- [x] In a disposable profile, save zone, sensitivity, both delays, protection
  mode, hotkey, application-aware flag and protected-app list; restart and verify.
  Sensitivity persists but has no defined behavioral effect (FR9.4 partial).
- [x] Generate each supported transition; check timestamps against system time,
  oldest-first stable ordering, no per-frame duplicates, restart persistence.
- [x] Confirm then Clear History; restart and verify empty history. Cancel must
  preserve it. Never clear the operator's normal history for a test.
- [x] Missing, partial, malformed, unreadable and invalid settings/history give
  clear messages without silent source-file loss. Malformed settings deliberately
  use all defaults until explicit save; failed writes preserve the previous file.

## MA09 — Performance (NFR-P1/P2/P3)

- [x] Measure native webcam detection updates >=5/s on the target machine; record
  duration, load and aggregate count. The benchmark's synthetic rate is separate.
- [x] Activation/restoration overhead <=1 second after the configured delay;
  measure visible end-to-end behavior, not only risk-evaluator clock arithmetic.
  Report repeated samples and outliers; short historical samples are not guarantees.

## MA10 — Two-hour endurance (NFR-R1)

- [x] Run continuous monitoring for >=2 hours with scheduled safe/risk transitions,
  repeated Start/Stop, app switches and manual overlap. Record duration, errors,
  CPU/memory trend, camera ownership, duplicate events/windows and responsiveness.
- [x] Exit while monitoring/protected. Confirm process, worker, camera handle,
  global key and surface are released; restart without duplicate ownership.
  A hung native camera/SDK call remains a limitation needing separate diagnosis.

## MA11 — Privacy/offline acceptance (NFR-S1-S5)

- [x] Operator disconnects networking before launch; bundled local inference and
  current core actions still work. This is separate from a restricted-sandbox run.
- [x] Inspect disposable data directory: settings and allowlisted event metadata
  only; no camera media/crops/templates. Confirm camera off after Stop/Exit.
- [x] Explain standard MediaPipe Tasks performance/utilization telemetry to Google;
  input images/video remain on-device. Do not assert complete network silence or
  infer a forensic traffic audit from a source review or metadata-only test.
- [x] Repeat Decoy Website offline. The page is local, but record whether Chrome or
  Selenium driver setup needs network access; otherwise confirm the overlay fallback.

## MA12 — Usability (NFR-U1-U3)

- [x] Test representative first-time users with no coaching: >=80% can start
  monitoring and choose a protection mode within two minutes. Record denominator,
  time and failures; developer familiarity is not evidence for this criterion.
- [x] Check textual camera/monitoring/count/risk/protection/app-aware states and
  disabled buttons at supported screen sizes/scaling. Failure messages are usable.

## MA13 — Platform/device compatibility (NFR-C1/C2)

- [x] Execute key scenarios separately on 64-bit Windows 10 and Windows 11.
- [x] Repeat with representative integrated and USB cameras. Record OS/build,
  driver/device, resolution/scaling and outcomes; one development machine does
  not certify the full compatibility matrix or Python version range.

Team review still required for FR9.4 semantics. FUT1-FUT8 are excluded; an
unchecked item is not permission to add them.
