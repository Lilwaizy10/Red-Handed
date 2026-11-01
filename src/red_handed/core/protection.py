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
    def open(self) -> None: ...
    def close(self) -> None: ...


class ProtectionManager:
    def __init__(self, state, web_opener: WebOpener, surface: ProtectionSurface, mode=ProtectionMode.PRIVACY_OVERLAY):
        self.state, self.surface = state, surface
        self.web_opener = web_opener
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
        desired = ((self.state.selected_protection_mode, self.state.test_protection_requested, self.source)
                   if self.source else None)
        if desired == self._presentation and not self.state.protection_error:
            return
        began = perf_counter()
        try:
            if desired is None:
                self.surface.hide()
                self.web_opener.close()
            elif desired[0] is ProtectionMode.DECOY_WEBSITE:
                if self._presentation is None or self._presentation[0] is not ProtectionMode.DECOY_WEBSITE:
                    self.web_opener.open()
                
                self.surface.hide()
            else:
                self.web_opener.close()
                self.surface.show(desired[0], test=desired[1], source=desired[2])
        except Exception as error:
            # UC15.EX.1: do not claim a failed presentation is protecting the screen.
            self.state.protection_error = f"Protection Surface/Decoy Window failed: {error}"
            try:
                self.web_opener.close()
            except Exception:
                pass
            '''
            #scenario where can close privacy overlay/screen blackout 
            #screen but cannot open decoy website (rollback option)
            if( 
                self._presentation is not None 
                and self._presentation[0] is not ProtectionMode.DECOY_WEBSITE 
                and desired is not None
                and desired[0] is ProtectionMode.DECOY_WEBSITE
            ):
            '''
                
                #previous = self._presentation
                #self.surface.show(previous[0], test=previous[1], source=previous[2])
        else:
            self._presentation = desired
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
                        self.state.selected_protection_mode,
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
                self.web_opener.close()
            finally:
                self.state.protection_active = False
                self.state.automatic_protection_requested = False
                self.state.manual_protection_requested = False
                self.state.test_protection_requested = False
                self._presentation = None
                self._automatic_requested = False