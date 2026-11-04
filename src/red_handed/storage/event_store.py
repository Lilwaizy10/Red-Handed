"""FR11 / NFR-R4: local atomic JSON history; malformed input is never overwritten."""

import json
import os
from pathlib import Path
import tempfile

from red_handed.core.events import PrivacyEvent
from red_handed.storage.settings_store import default_settings_path, backup_damaged_file


class EventStore:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else default_settings_path().with_name('events.json')
        self.last_error = None

    def load(self):
        self.last_error = None
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if (not isinstance(data, dict) or set(data) != {'version', 'events'}
                    or type(data['version']) is not int or data['version'] != 1):
                raise ValueError('Unsupported event history format.')
            if not isinstance(data['events'], list):
                raise ValueError('Invalid event collection.')
            events = [PrivacyEvent.from_dict(item) for item in data['events']]
            return sorted(events, key=lambda event: event.timestamp)
        except FileNotFoundError:
            return []
        except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
            self.last_error = 'Event history unavailable; original file preserved. Check file access or use Clear History to reset it.'
            return []

    def _write(self, events):
        text = json.dumps({'version': 1, 'events': [event.to_dict() for event in events]}, indent=2) + '\n'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.path.parent,
                                             prefix='events-', suffix='.tmp', delete=False) as file:
                temporary = Path(file.name)
                file.write(text)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.path)
            self.last_error = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def append(self, event):
        if not isinstance(event, PrivacyEvent):
            raise ValueError('Only validated event metadata may be stored.')
        events = self.load()
        if self.last_error:
            raise OSError(self.last_error)
        self._write([*events, event])

    def clear(self):
        # FR11.4: a confirmed Clear may replace a malformed file, but keeps a copy.
        if self.path.exists():
            self.load()
            if self.last_error:
                backup_damaged_file(self.path)
        self._write([])