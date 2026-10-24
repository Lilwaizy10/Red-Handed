"""Deterministic helpers for controller tests; no camera, threads, or sleeps."""

from concurrent.futures import Executor, Future
from dataclasses import dataclass


class FakeClock:
    """A monotonic clock that the test advances explicitly."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@dataclass(frozen=True)
class FakeFrame:
    """Immutable frame metadata sufficient for a mocked detector."""

    shape: tuple[int, int, int] = (100, 200, 3)

    def copy(self):
        # Return a separate object, matching the controller's ownership contract.
        return FakeFrame(self.shape)


class ImmediateExecutor(Executor):
    """Execute immediately while preserving the controller's Future interface."""

    def submit(self, function, /, *args, **kwargs):
        future = Future()
        try:
            future.set_result(function(*args, **kwargs))
        except Exception as error:
            # Worker failures must be raised when the controller reads the result.
            future.set_exception(error)
        return future

    def shutdown(self, wait=True, *, cancel_futures=False):
        # No threads or native resources exist in this test executor.
        pass


def read_detection(controller, clock):
    """Submit and collect one detection without racing a background thread."""
    frame = controller.read_frame()
    controller.read_frame()

    # Both reads use the same timestamp, preventing a second submission.
    # Advance afterward so the next observation passes the 0.1-second throttle.
    clock.now += 0.25
    return frame