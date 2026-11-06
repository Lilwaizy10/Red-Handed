# Requirements traceability

Automated checks, synthetic demonstrations and physical acceptance are
recorded separately. An implementation or test reference does not by itself
establish a pass. See the [final report](final_report.md) for recorded results.

| Requirement | Implementation | Verification evidence | Status or gap |
|---|---|---|---|
| FR1, FR12, FR13 — monitoring, status and camera recovery | `detection/camera.py`, `core/monitoring.py`, `ui/main_window.py` | `test_monitoring.py`; `test_acceptance.py` S2; MA01/MA07 | Record automated and physical results separately |
| FR2–FR3 — face count and saved privacy zone | `detection/person_detector.py`, `detection/privacy_zone.py`, `ui/zone_preview.py` | `test_zone_monitoring.py`; `test_zone_settings_ui.py`; MA01/MA03 | Geometry and settings checks do not establish detector accuracy |
| FR4 — activation and recovery timing | `core/privacy_risk.py`, `core/monitoring.py` | `test_privacy_risk.py`; `test_risk_pipeline.py`; `test_acceptance.py` S1 | Automated timing uses controlled observations |
| FR5–FR7, FR10 — protection and emergency actions | `core/protection.py`, `ui/protection_surface.py`, `system/hotkey_manager.py` | `test_protection_integration.py`; `test_decoy_protection.py`; MA04/MA05 | Record real display and physical shortcut results separately |
| FR8 — application-aware protection | `core/applications.py`, `system/active_application.py`, `ui/main_window.py` | `test_phase5_integration.py`; MA06 | Confirm foreground switching on Windows |
| FR9 — settings | `core/settings.py`, `storage/settings_store.py` | `test_zone_settings_ui.py`; MA08 | FR9.4 partial: stored sensitivity has no defined effect |
| FR11 — event history | `core/events.py`, `storage/event_store.py`, `ui/event_history_view.py` | `test_phase5_integration.py`; MA08 | Record save, restart and confirmed Clear results |
| NFR-D1/D2 — detection quality and false activations | `detection/person_detector.py`, `core/monitoring.py` | MA02 controlled scenarios and aggregate counts | Unverified until counts and denominators are available |
| NFR-P1–P4 — throughput and latency | `core/monitoring.py`, `core/protection.py`, `system/hotkey_manager.py` | MA05/MA09; native benchmark for throughput | Synthetic timing does not verify physical latency |
| NFR-R1 — two-hour endurance | `core/monitoring.py`, `ui/main_window.py` | MA10 timed session record | Unverified until a timed run is documented |
| NFR-S1–S5 — privacy and offline behaviour | `detection/person_detector.py`, `core/events.py`, `storage/event_store.py` | MA11 offline and data-directory checks | Disclose telemetry; record offline results separately |
| NFR-U1–U3 — usability | `ui/main_window.py`, `ui/tutorial_controller.py` | Tutorial tests; MA12 first-time-user results | Automated navigation does not verify the user-study target |
| NFR-C1/C2 — Windows and camera compatibility | `launch_red_handed.bat`, `detection/camera.py` | MA13 machine/device results | List only configurations actually tested |