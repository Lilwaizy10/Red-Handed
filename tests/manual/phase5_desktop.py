"""Opt-in Phase 5 desktop harness; synthetic camera, real foreground/hotkey APIs.

Run: .venv/Scripts/python.exe -B tests/manual/phase5_desktop.py
Optional --directory PATH retains only settings/events for process-restart checks.
Never pass the real user settings directory. No images or video are stored.
"""

import argparse
from pathlib import Path
import subprocess
import sys
import tempfile
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))

from red_handed.core.monitoring import MonitoringController
from red_handed.core.settings import MonitoringSettings
from red_handed.detection.person_detector import DetectionResult
from red_handed.detection.privacy_zone import PrivacyZone
from red_handed.storage.event_store import EventStore
from red_handed.storage.settings_store import SettingsStore, default_settings_path
from red_handed.ui.main_window import MainWindow


def focus_target():
    root = tk.Tk()
    root.title('Phase 5 protected focus target')
    root.geometry('650x240+100+100')
    tk.Label(root, text='SYNTHETIC DEMO CONTENT\nProtect this Python executable.',
             fg='red', font=('Segoe UI', 24), wraplength=600).pack(expand=True)
    root.after(900000, root.destroy)
    root.mainloop()


def run(directory):
    import numpy as np

    class Camera:
        available, is_open, last_error = True, False, 'Synthetic camera unavailable'
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        def check_availability(self):
            return self.available
        def open(self):
            self.is_open = self.available
            return self.is_open
        def read_frame(self):
            return self.frame if self.available and self.is_open else None
        def release(self):
            self.is_open = False

    class Detector:
        inside = False
        def detect(self, frame):
            return DetectionResult(2, ((0, 0, 100, 100), (220 if self.inside else 20, 120, 20, 20)))

    if directory.resolve() == default_settings_path().parent.resolve():
        raise ValueError('Use a disposable validation directory, not real user settings.')
    store = SettingsStore(directory / 'settings.json')
    if not store.path.exists():
        store.save(MonitoringSettings(PrivacyZone(.5, 0, .5, 1), activation_delay=0, recovery_delay=0))
    
    camera, detector = Camera(), Detector()
    root = tk.Tk()
    controller = MonitoringController(camera=camera, detector=detector, settings=store.load())
    window = MainWindow(root, controller, store)
    recorder = window.recorder
    root.report_callback_exception = lambda *error: print('CALLBACK ERROR', error, flush=True)
    target = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()), '--focus-target'])
    panel = tk.Toplevel(root)
    panel.title('Phase 5 validation controls')
    panel.geometry('530x360+60+80')

    def risk():
        window.start_monitoring()
        root.after(5000, lambda: setattr(detector, 'inside', True))
    def pulse():
        risk()
        root.after(30000, lambda: setattr(detector, 'inside', False))
    def camera_off():
        camera.available = False
        # Use the normal read-failure transition when monitoring is running.
        if not camera.is_open:
            window.retry_camera()
    def camera_on():
        camera.available = True
        window.retry_camera()

    for label, callback in [('Start persistent risk in 5 seconds', risk),
                            ('Risk pulse: starts in 5s, clears at 30s', pulse),
                            ('Clear risk', lambda: setattr(detector, 'inside', False)),
                            ('Camera unavailable', camera_off), ('Camera available', camera_on),
                            ('Close Red-Handed', window.close)]:
        tk.Button(panel, text=label, command=callback).pack(fill=tk.X, padx=12, pady=4)
    tk.Label(panel, text='Temporary test configuration. Real foreground detector.\n'
             'Add the executable printed in the terminal to Protected Applications.').pack()
    print('DIRECTORY', directory, 'TARGET_EXECUTABLE', sys._base_executable, flush=True)
    print('RELOADED', store.application_settings, 'EVENT_COUNT', len(recorder.events()), flush=True)
    last = None
    def report():
        nonlocal last
        state = controller.state
        snapshot = (str(state.risk_status), state.protection_active, state.automatic_protection_requested,
                    state.manual_protection_requested, window._last_external_application.executable_path,
                    recorder.revision, recorder.last_error)
        if snapshot != last:
            print('STATE', snapshot, flush=True)
            if last is None or recorder.revision != last[-2]:
                print('EVENTS', [e.to_dict() for e in recorder.events()], flush=True)
            last = snapshot
        root.after(200, report)
    report()
    root.after(900000, window.close)
    try:
        root.mainloop()
    finally:
        window.close()
        if target.poll() is None:
            target.terminate()  # Only the disposable helper created above.
            target.wait(timeout=5)
        print('CLEANUP', not camera.is_open, controller._executor is None,
              window.surface.window is None, 'SAVED_EVENTS', len(EventStore(directory / 'events.json').load()), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path)
    parser.add_argument('--focus-target', action='store_true')
    args = parser.parse_args()
    if args.focus_target:
        focus_target()
    elif args.directory:
        run(args.directory)
    else:
        with tempfile.TemporaryDirectory(prefix='red-handed-phase5-') as directory:
            run(Path(directory))
