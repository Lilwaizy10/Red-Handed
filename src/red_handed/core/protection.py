"""FR5 / FR6 / FR10: source arbitration, independent of Tk and camera acquisition."""

from time import perf_counter
from typing import Protocol

from red_handed.core.privacy_risk import RiskStatus
from red_handed.core.settings import ProtectionMode


class ProtectionSurface(Protocol):
    def show(self, mode: ProtectionMode, *, test: bool, source: str) -> None: ...
    def hide(self) -> None: ...
    def close(self) -> None: ...


class ProtectionManager:
    def __init__(self, state, surface: ProtectionSurface, mode=ProtectionMode.PRIVACY_OVERLAY):
        self.state, self.surface = state, surface
        self.state.selected_protection_mode = mode
        self._presentation = None
        self._uncertain = False
        self._safe_since = None
        self._closed = False
        self.last_transition_seconds = 0.0

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
        desired = ((self.state.selected_protection_mode, self.state.test_protection_requested, self.source)
                   if self.source else None)
        if desired == self._presentation and not self.state.protection_error:
            return
        began = perf_counter()
        try:
            if desired is None:
                self.surface.hide()
            else:
                self.surface.show(desired[0], test=desired[1], source=desired[2])
        except Exception as error:
            # UC15.EX.1: do not claim a failed presentation is protecting the screen.
            self.state.protection_error = f"Protection surface failed: {error}"
        else:
            self._presentation = desired
            self.state.protection_active = desired is not None
            self.state.protection_error = None
        self.last_transition_seconds = perf_counter() - began

    def select_mode(self, mode):
        if not isinstance(mode, ProtectionMode):
            raise ValueError('Invalid protection mode.')
        self.state.selected_protection_mode = mode
        self._sync()

    def set_automatic(self, active):
        self.state.automatic_protection_requested = bool(active)
        if active:
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
            if self.state.automatic_protection_requested:
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
            self.state.protection_active = False
            self.state.automatic_protection_requested = False
            self.state.manual_protection_requested = False
            self.state.test_protection_requested = False
            self._presentation = None