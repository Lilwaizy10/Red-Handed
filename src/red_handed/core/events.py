"""FR11: strict metadata-only events and a failure-isolated recording service."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from threading import Lock

from red_handed.core.settings import ProtectionMode


class EventType(str, Enum):
    RISK_DETECTED = 'Privacy risk detected'
    AUTOMATIC_ACTIVATED = 'Automatic protection activated'
    AUTOMATIC_DEACTIVATED = 'Automatic protection deactivated'
    MANUAL_ACTIVATED = 'Manual protection activated'
    MANUAL_DEACTIVATED = 'Manual protection deactivated'
    CAMERA_UNAVAILABLE = 'Camera unavailable'


class EventAction(str, Enum):
    RISK_ACTIVE = 'Risk active'
    PROTECTED = 'Display protected'
    STILL_PROTECTED = 'Display remains protected'
    RESTORED = 'Display restored'
    CAMERA_UNAVAILABLE = 'Monitoring unavailable'


@dataclass(frozen=True)
class PrivacyEvent:
    timestamp: datetime
    event_type: EventType
    action: EventAction
    protection_mode: ProtectionMode | None = None

    def __post_init__(self):
        if not isinstance(self.timestamp, datetime) or self.timestamp.utcoffset() is None:
            raise ValueError('Event timestamp must include a timezone.')
        if not isinstance(self.event_type, EventType) or not isinstance(self.action, EventAction):
            raise ValueError('Invalid event type/action.')
        if self.protection_mode is not None and not isinstance(self.protection_mode, ProtectionMode):
            raise ValueError('Invalid event protection mode.')

    def to_dict(self):
        # NFR-S4: allowlisted scalar metadata; no arbitrary payload or free-form text.
        return {'timestamp': self.timestamp.isoformat(), 'event_type': self.event_type.value,
                'action': self.action.value,
                'protection_mode': self.protection_mode.value if self.protection_mode else None}

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or set(data) != {'timestamp', 'event_type', 'action', 'protection_mode'}:
            raise ValueError('Invalid event fields.')
        return cls(datetime.fromisoformat(data['timestamp']), EventType(data['event_type']),
                   EventAction(data['action']),
                   ProtectionMode(data['protection_mode']) if data['protection_mode'] is not None else None)


class EventRecorder:
    """One ordered writer off the UI thread. No store means explicit in-memory use.

    A failed write pauses recording until a successful explicit Clear. Existing
    records are retained; no retry loop can block protection or spam errors.
    """

    def __init__(self, store=None, clock=lambda: datetime.now(timezone.utc)):
        self.store, self.clock = store, clock
        self._lock = Lock()
        self._events = store.load() if store is not None else []
        self.last_error = store.last_error if store is not None else None
        self.revision = 0
        self._closed = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='red-handed-events') if store else None

    def record(self, event_type, action, protection_mode=None):
        if self._closed or self.last_error:
            return False
        try:
            event = PrivacyEvent(self.clock(), event_type, action, protection_mode)
            if self._executor is None:
                self._append(event)
            else:
                self._executor.submit(self._append, event)
            return True
        except Exception:
            self.last_error = 'Event recording unavailable; privacy protection remains operational.'
            self.revision += 1
            return False

    def _append(self, event):
        if self.last_error:
            return
        try:
            if self.store is not None:
                self.store.append(event)
            with self._lock:
                self._events.append(event)
                self.revision += 1
        except Exception:
            self.last_error = 'Event storage unavailable. Recording paused; existing history is preserved. Clear History to reset.'
            self.revision += 1

    def events(self):
        with self._lock:
            return sorted(self._events, key=lambda event: event.timestamp)

    def flush(self):
        if self._executor is not None and not self._closed:
            self._executor.submit(lambda: None).result()

    def clear(self):
        def clear_records():
            try:
                if self.store is not None:
                    self.store.clear()
                with self._lock:
                    self._events.clear()
                    self.last_error = None
                    self.revision += 1
                return True
            except Exception:
                self.last_error = 'History could not be cleared; existing records are preserved.'
                self.revision += 1
                return False
        if self._closed:
            return False
        return self._executor.submit(clear_records).result() if self._executor else clear_records()

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._executor is not None:
            self._executor.shutdown(wait=True)