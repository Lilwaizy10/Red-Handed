"""Opt-in MediaPipe benchmark / isolated desktop smoke helper. Never saves frames.

Default: synthetic 1280x720 pixels through the real detector/controller.
--camera: real default webcam, owned only by CameraManager.
--desktop: real MainWindow, temporary settings/history, real native hotkey.
Close that window to finish; a two-minute safety timeout also closes it.
Numbers measure update throughput, not person-classification accuracy.
"""

import argparse
from pathlib import Path
import sys
import tempfile
from time import monotonic, sleep

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from red_handed.core.monitoring import MonitoringController
from red_handed.detection.camera import CameraManager
from red_handed.detection.person_detector import PersonDetector


class SyntheticCamera:
    last_error = None
    is_open = False

    def __init__(self):
        self.frame = np.random.default_rng(55).integers(0, 256, (720, 1280, 3), dtype=np.uint8)

    def check_availability(self):
        return True

    def open(self):
        self.is_open = True
        return True

    def read_frame(self):
        return self.frame if self.is_open else None

    def release(self):
        self.is_open = False


def benchmark(camera, seconds):
    controller = MonitoringController(camera=camera, detector=PersonDetector())
    updates, previous, counts = [], None, set()
    try:
        if not controller.start_monitoring():
            raise RuntimeError(controller.state.camera_error)
        # Warm up the lazy model/import separately from the timed update interval.
        deadline = monotonic() + 30
        while controller.state.detection is None and monotonic() < deadline:
            controller.read_frame()
            if controller.state.detection_error:
                raise RuntimeError(controller.state.detection_error)
            sleep(.033)
        if controller.state.detection is None:
            raise RuntimeError('No valid detector result during warm-up.')
        previous = controller.state.detection
        began = monotonic()
        while monotonic() - began < seconds:
            controller.read_frame()
            observed = controller.state.detection
            if observed is not None and observed is not previous:
                updates.append(monotonic())
                counts.add(observed.person_count)
                previous = observed
            sleep(.033)
        elapsed = monotonic() - began
        print('BENCHMARK', 'camera' if isinstance(camera, CameraManager) else 'synthetic',
              'updates', len(updates), 'seconds', round(elapsed, 3),
              'updates_per_second', round(len(updates) / elapsed, 2),
              'observed_counts', sorted(counts), 'error', controller.state.detection_error, flush=True)
    finally:
        controller.close()
        print('CLEANUP', 'camera_released', not camera.is_open,
              'worker_joined', controller._executor is None,
              'detector_closed', controller.detector._closed, flush=True)


def desktop(camera):
    import tkinter as tk
    
    from red_handed.core.settings import MonitoringSettings
    from red_handed.detection.privacy_zone import PrivacyZone
    
    from red_handed.storage.settings_store import SettingsStore
    from red_handed.ui.main_window import MainWindow

    with tempfile.TemporaryDirectory(prefix='red-handed-phase5-5-') as directory:
        store = SettingsStore(Path(directory) / 'settings.json')
        store.save(MonitoringSettings(PrivacyZone(.5, 0, .5, 1), activation_delay=1, recovery_delay=1))
        
        root = tk.Tk()
        controller = MonitoringController(camera=camera, detector=PersonDetector(), settings=store.load())
        window = MainWindow(root, controller, store)
        errors, updates = [], []
        previous = None
        last_state = None
        root.report_callback_exception = lambda *error: errors.append(str(error[1]))

        def report():
            nonlocal previous, last_state
            state = controller.state
            if state.detection is not None and state.detection is not previous:
                updates.append(monotonic())
                previous = state.detection
            snapshot = (state.monitoring_status.value, state.camera_status.value,
                        state.detection.person_count if state.detection else None,
                        str(state.risk_status), state.protection_active, state.detection_error)
            if snapshot != last_state:
                print('STATE', snapshot, flush=True)
                last_state = snapshot
            root.after(20, report)

        report()
        root.after(120000, window.close)
        print('DESKTOP', 'real webcam' if isinstance(camera, CameraManager) else 'synthetic pixels',
              'temporary settings and history; no camera media stored', flush=True)
        try:
            root.mainloop()
        finally:
            window.close()
            print('DESKTOP_CLEANUP', not camera.is_open, controller._executor is None,
                  controller.detector._closed, window.surface.window is None,
                  'callback_errors', errors, 'detection_updates', len(updates), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--camera', action='store_true')
    parser.add_argument('--desktop', action='store_true')
    parser.add_argument('--seconds', type=float, default=10)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 120:
        parser.error('--seconds must be between 1 and 120')
    camera = CameraManager() if args.camera else SyntheticCamera()
    desktop(camera) if args.desktop else benchmark(camera, args.seconds)
