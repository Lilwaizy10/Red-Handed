# Red-Handed

Red-Handed is a Windows desktop privacy-protection system intended to reduce shoulder-surfing by detecting additional people within a configured privacy zone and activating a selected screen-protection mode.

**Current status:** Initial project skeleton

**Initial target:** 64-bit Windows 10 and Windows 11

Implementation has not started yet; technology-stack decisions are still pending.

## Folder structure

```text
docs/                   SC2006 laboratory documentation
src/red_handed/         Provisional Python application package
  core/                 Monitoring, risk, protection, and runtime state
  detection/            Camera, person detection, and privacy-zone concerns
  ui/                   User-interface views and controls
  storage/              Settings and metadata-only event persistence
  system/               Windows hotkey and active-application integration
tests/                   Unit and integration test suites
```

Future enhancements FUT1–FUT8 are currently out of scope.
