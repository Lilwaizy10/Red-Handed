from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from types import TracebackType
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class VideoCaptureLike(Protocol):
    def isOpened(self) -> bool: ...
    def read(self) -> tuple[bool, Any]: ...
    def release(self) -> None: ...


class CameraManager:
    def __init__(
        self,
        camera_index: int = 0,
        capture_factory: Callable[[int], VideoCaptureLike] | None = None,
    ) -> None:
        self.camera_index = camera_index
        self._capture_factory = capture_factory
        self._capture: VideoCaptureLike | None = None
        self.last_error: str | None = None

    # context manager
    def __enter__(self) -> CameraManager:
        if not self.open():
            raise RuntimeError(self.last_error or "Failed to open camera.")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()

    # internals
    def _create_capture(self) -> VideoCaptureLike:
        if self._capture_factory is not None:
            return self._capture_factory(self.camera_index)
        try:
            import cv2
        except ImportError as exc:
            raise ImportError(
                "OpenCV is required for CameraManager but is not installed."
            ) from exc

        if sys.platform == "win32":
            capture = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
            if capture.isOpened():
                return capture
            capture.release()

        return cv2.VideoCapture(self.camera_index)

    @staticmethod
    def _is_opened(capture: VideoCaptureLike | None) -> bool:
        if capture is None:
            return False
        try:
            return bool(capture.isOpened())
        except Exception:
            logger.debug("isOpened() raised", exc_info=True)
            return False

    # public API
    @property
    def is_opened(self) -> bool:
        return self._is_opened(self._capture)

    def check_availability(self) -> bool:
        # A second probe on an already-held device can fail (e.g. DirectShow).
        if self.is_opened:
            self.last_error = None
            return True

        probe = None
        try:
            probe = self._create_capture()
            if not self._is_opened(probe):
                self.last_error = "Camera is not available."
                return False
            self.last_error = None
            return True
        except Exception as e:
            self.last_error = f"Error checking camera availability: {e}"
            return False
        finally:
            if probe is not None:
                try:
                    probe.release()
                except Exception:
                    logger.debug("Probe release failed", exc_info=True)

    def open(self) -> bool:
        if self.is_opened:
            return True

        self.release()
        try:
            self._capture = self._create_capture()
            if not self._is_opened(self._capture):
                self.release()
                self.last_error = "Failed to open camera."
                return False
            self.last_error = None
            return True
        except Exception as e:
            self.release()
            self.last_error = f"Error opening camera: {e}"
            return False

    def read_frame(self) -> Any | None:
        capture = self._capture
        if not self._is_opened(capture):
            self.last_error = "Camera is not opened."
            return None
        try:
            ret, frame = capture.read()
        except Exception as e:
            self.last_error = f"Error reading frame: {e}"
            return None
        if not ret or frame is None:
            self.last_error = "Failed to read frame from camera."
            return None
        self.last_error = None
        return frame

    def release(self) -> None:
        capture, self._capture = self._capture, None
        if capture is not None:
            try:
                capture.release()
            except Exception:
                logger.debug("Capture release failed", exc_info=True)