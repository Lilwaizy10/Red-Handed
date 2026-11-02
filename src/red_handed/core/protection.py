"""FR5 / FR6 / FR10: source arbitration, independent of Tk and camera acquisition."""

from time import perf_counter
from typing import Protocol

from red_handed.core.privacy_risk import RiskStatus
from red_handed.core.settings import ProtectionMode
from red_handed.core.events import EventType, EventAction


class ProtectionSurface(Protocol):
    def show(self, mode: ProtectionMode, *, test: bool, source: str) -> None: ...
    def hide(self) -> None: ...
    def close(self) -> None: ...

class WebOpener(Protocol):
    ready: bool
    starting: bool
    last_error: str | None

    def open(self) -> None: ...
    def close(self) -> None: ...
    def shutdown(self) -> None: ...


class ProtectionManager:
    def __init__(
        self,
        state,
        surface: ProtectionSurface,
        mode=ProtectionMode.PRIVACY_OVERLAY,
        *,
        web_opener: WebOpener | None = None,
    ):
        self.state, self.surface = state, surface
        self.web_opener = web_opener
        self.active_mode = None
        self.notice = None
        self.state.selected_protection_mode = mode
        self._presentation = None
        self._uncertain = False
        self._safe_since = None
        self._closed = False
        self.last_transition_seconds = 0.0
        # Keep the underlying automatic request separate from the app gate.
        # Switching applications must not reset privacy-risk timing.
        self._automatic_requested = False
        self._application_allowed = True

        self.recorder = None
        self._recorded_requests = (False, False)

    @property
    def source(self):
        sources = []
        if self.state.automatic_protection_requested:
            sources.append('Automatic')
        if self.state.manual_protection_requested:
            sources.append('Manual')
        if self.state.test_protection_requested:
            sources.append('TEST MODE')
        return ' + '.join(sources)

    def _sync(self):
        if self._closed:
            return
        self.state.automatic_protection_requested = (
            self._automatic_requested and self._application_allowed
        )
        desired = ((self.state.selected_protection_mode,
                    self.state.test_protection_requested, self.source)
                   if self.source else None)
        decoy = desired is not None and desired[0] is ProtectionMode.DECOY_WEBSITE
        # Check the browser even when the protection request has not changed.
        if desired == self._presentation and not self.state.protection_error and not decoy:
            return

        began = perf_counter()
        try:
            notice = None
            if desired is None:
                self.surface.hide()
                if self.web_opener is not None:
                    self.web_opener.close()
                actual_mode = None
            elif decoy:
                if self.web_opener is None:
                    raise RuntimeError("No decoy browser is configured.")
                self.web_opener.open()
                if self.web_opener.ready:
                    actual_mode = ProtectionMode.DECOY_WEBSITE
                    if self.active_mode is not actual_mode:
                        self.surface.hide()
                else:
                    # Cover the screen while Chrome starts, recovers or fails.
                    actual_mode = ProtectionMode.PRIVACY_OVERLAY
                    if self.web_opener.last_error:
                        notice = "Decoy unavailable; Privacy Overlay is active. " + self.web_opener.last_error
                    else:
                        notice = "Decoy starting; Privacy Overlay is active."
                    if self.active_mode is not actual_mode or desired != self._presentation:
                        self.surface.show(actual_mode, test=desired[1], source=desired[2])
            else:
                actual_mode = desired[0]
                self.surface.show(actual_mode, test=desired[1], source=desired[2])
                if self.web_opener is not None:
                    self.web_opener.close()
        except Exception as error:
            # Clear the previous result so the next attempt actually retries.
            self._presentation = None
            self.active_mode = None
            self.notice = None
            self.state.protection_active = False
            self.state.protection_error = f"Protection failed: {error}"
            if self.web_opener is not None:
                try:
                    self.web_opener.close()
                except Exception:
                    pass
        else:
            self._presentation = desired
            self.active_mode = actual_mode
            self.notice = notice
            self.state.protection_active = desired is not None
            self.state.protection_error = None
            self._record_transitions()
        self.last_transition_seconds = perf_counter() - began

    def set_application_allowed(self, allowed):
        """Reapply the automatic gate without touching risk or manual requests."""
        self._application_allowed = bool(allowed)
        self._sync()

    def _record_transitions(self):
        """Record request transitions only after successful presentation."""
        current = (
            self.state.automatic_protection_requested,
            self.state.manual_protection_requested,
        )
        previous = self._recorded_requests

        if self.recorder is not None:
            if not self.state.protection_active:
                action = EventAction.RESTORED
            elif any(previous):
                action = EventAction.STILL_PROTECTED
            else:
                action = EventAction.PROTECTED

            transitions = (
                (
                    previous[0],
                    current[0],
                    EventType.AUTOMATIC_ACTIVATED,
                    EventType.AUTOMATIC_DEACTIVATED,
                ),
                (
                    previous[1],
                    current[1],
                    EventType.MANUAL_ACTIVATED,
                    EventType.MANUAL_DEACTIVATED,
                ),
            )
            for before, after, activated, deactivated in transitions:
                if before != after:
                    self.recorder.record(
                        activated if after else deactivated,
                        action,
                        self.active_mode or self.state.selected_protection_mode,
                    )

        # Unchanged observations must never produce a row per camera frame.
        self._recorded_requests = current

    def select_mode(self, mode):
        if not isinstance(mode, ProtectionMode):
            raise ValueError('Invalid protection mode.')
        self.state.selected_protection_mode = mode
        self._sync()

    def set_automatic(self, active):
        # Preserve the risk-derived request even while the app gate blocks it.
        self._automatic_requested = bool(active)

        if active and self._application_allowed:
            self.state.test_protection_requested = False

        self._sync()

    def toggle_manual(self):
        """FR10.2 / FR13.5: deliberately no camera or detector precondition."""
        if self.state.test_protection_requested:
            self.end_test()
            return
        self.state.manual_protection_requested = not self.state.manual_protection_requested
        self._sync()

    def observe_risk(self, status, inside, sampled_at, recovery_delay):
        """Normal transitions reuse Phase 3 timing; unknown evidence never reveals.

        After lost evidence, require a fresh continuous safe recovery interval.
        Repeated UI ticks cannot advance this guard: it uses capture timestamps.
        """
        if status is None or sampled_at is None:
            if self._automatic_requested:
                self._uncertain = True
                self._safe_since = None
            return
        if status in (RiskStatus.ACTIVE, RiskStatus.PENDING_RECOVERY):
            self._uncertain, self._safe_since = False, None
            self.set_automatic(True)
        elif self._uncertain:
            if inside is not False:
                self._safe_since = None
            else:
                if self._safe_since is None:
                    self._safe_since = sampled_at
                if sampled_at - self._safe_since >= recovery_delay:
                    self._uncertain, self._safe_since = False, None
                    self.set_automatic(False)
        else:
            self.set_automatic(False)

    def stop_automatic(self):
        """Explicit Stop acknowledges restoration of automatic protection only."""
        self._uncertain, self._safe_since = False, None
        self.set_automatic(False)

    def begin_test(self):
        if self.state.automatic_protection_requested or self.state.manual_protection_requested:
            raise ValueError('Protection is already active. Clear its requests before testing.')
        self.state.test_protection_requested = True
        self._sync()

    def end_test(self):
        self.state.test_protection_requested = False
        self._sync()

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self.surface.close()
        finally:
            try:
                if self.web_opener is not None:
                    self.web_opener.shutdown()
            finally:
                self.state.protection_active = False
                self.state.automatic_protection_requested = False
                self.state.manual_protection_requested = False
                self.state.test_protection_requested = False
                self._presentation = None
                self._automatic_requested = False
                self.active_mode = None
                self.notice = None
