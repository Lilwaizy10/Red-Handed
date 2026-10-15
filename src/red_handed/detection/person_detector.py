"""On-device face counting; no camera access, identity matching, or image storage.

MediaPipe Tasks sends performance/utilization telemetry, not input images/video.
Hence, this application is not network-silent.
"""

from dataclasses import dataclass
from math import isfinite
from numbers import Real
from pathlib import Path
from typing import Any

def has_additional_person(person_count: int) -> bool:
    """FR2.2: assume one visible person is the primary user; never infer identity."""
    if person_count < 0:
        raise ValueError("Person count cannot be negative.")
    return person_count >= 2


@dataclass(frozen=True)
class DetectionResult:
    """Only the current count and face boxes, in original-frame coordinates.

    Each box is ``(left, top, width, height)`` in pixels.
    """

    person_count: int
    bounding_boxes: tuple[tuple[int, int, int, int], ...] = ()

    def __post_init__(self) -> None:
        if (isinstance(self.person_count, bool)
                or not isinstance(self.person_count, int)):
            raise ValueError("Person count must be an integer.")
        if self.person_count < 0:
            raise ValueError("Person count cannot be negative.")

    @property
    def additional_person_present(self) -> bool:
        return has_additional_person(self.person_count)


def _box_to_frame(x, y, width, height, source_width, source_height,
                  frame_width, frame_height):
    """Scale box edges and clip to the frame; preserve positive visible area.

    Tasks supplies pixels in the resized RGB input, not normalized coordinates.
    A source size of (1, 1) expresses the equivalent normalized conversion.
    Boxes entirely outside the picture or that rounds down to nothing are omitted.
    """
    values = (x, y, width, height, source_width, source_height,
              frame_width, frame_height)
    if (any(isinstance(v, bool) or not isinstance(v, Real) or not isfinite(v)
            for v in values)
            or min(width, height, source_width, source_height,
                   frame_width, frame_height) <= 0):
        raise ValueError("Face detector returned invalid box coordinates.")
    left = round(max(0, min(source_width, x)) * frame_width / source_width)
    top = round(max(0, min(source_height, y)) * frame_height / source_height)
    right = round(max(0, min(source_width, x + width)) * frame_width / source_width)
    bottom = round(max(0, min(source_height, y + height)) * frame_height / source_height)
    if right > left and bottom > top:
        return (left, top, right - left, bottom - top)
    return None


class _MediaPipeBackend:
    """All MediaPipe types stay inside this detection-layer adapter."""

    def __init__(self, model_path, confidence):
        import mediapipe as mp

        self._mp = mp
        options = mp.tasks.vision.FaceDetectorOptions(
            base_options=mp.tasks.BaseOptions(
                model_asset_path=str(model_path),
                delegate=mp.tasks.BaseOptions.Delegate.CPU,),
            running_mode=mp.tasks.vision.RunningMode.IMAGE,
            min_detection_confidence=confidence,
        )
        self._detector = mp.tasks.vision.FaceDetector.create_from_options(options)

    def detect(self, rgb):
        # Synchronous IMAGE mode: no second application frame queue or callback.
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        return self._detector.detect(image)

    def close(self):
        self._detector.close()


class PersonDetector:
    """Count faces without identity recognition, using one reusable CPU task.

    Lazy initialization keeps dependency/model failures off the UI startup path.
    One existing monitoring worker calls detect; close only after that worker
    has joined. Stop/restart reuses the task. No Haar fallback is performed.
    """

    MAX_FRAME_WIDTH = 480
    MIN_DETECTION_CONFIDENCE = 0.5  # Implementation parameter, NOT FR9.4 sensitivity.
    MODEL_PATH = Path(__file__).with_name("models") / "blaze_face_short_range.tflite"

    def __init__(self, *, model_path: Path | None = None,
                 min_detection_confidence: float = MIN_DETECTION_CONFIDENCE) -> None:
        if (isinstance(min_detection_confidence, bool)
                or not isinstance(min_detection_confidence, Real)
                or not isfinite(min_detection_confidence)
                or not 0 <= min_detection_confidence <= 1):
            raise ValueError("Detection confidence must be between 0 and 1.")
        self._model_path = Path(model_path) if model_path is not None else self.MODEL_PATH
        self._confidence = float(min_detection_confidence)
        self._backend: Any | None = None
        self._closed = False

    # FR2.1: analyse the existing camera pipeline's frame, without recognition.
    def detect(self, frame: Any) -> DetectionResult:
        """Return face count/regions, or raise an error for the controller to handle.

        The frame must be a non-empty uint8 BGR array (H, W, 3), as produced by
        OpenCV. The frame is never modified or stored.
        """
        import cv2
        import numpy as np

        if self._closed:
            raise RuntimeError("The face detector is closed.")
        if (
            not isinstance(frame, np.ndarray)
            or frame.dtype != np.uint8
            or frame.ndim != 3
            or frame.shape[2] != 3
            or frame.size == 0
        ):
            raise ValueError("Detection requires a non-empty uint8 BGR camera frame.")

        if self._backend is None:
            try:
                if not self._model_path.is_file():
                    raise FileNotFoundError(self._model_path)
                self._backend = _MediaPipeBackend(self._model_path, self._confidence)
            except Exception as error:
                raise RuntimeError(
                    "The local MediaPipe face detector could not be loaded.")

        height, width = frame.shape[:2]
        # NFR-P1: bound the work even if a webcam supplies high-resolution video.
        scale = min(1.0, self.MAX_FRAME_WIDTH / width)
        small = frame
        if scale < 1.0:
            small = cv2.resize(
                frame, (self.MAX_FRAME_WIDTH, max(1, round(height * scale))),
                interpolation=cv2.INTER_AREA,
            )
        # cvtColor makes a separate contiguous array; the preview's BGR frame is untouched.
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        result = self._backend.detect(rgb)
        try:
            if not isinstance(result.detections, (list, tuple)):
                raise ValueError("Missing detection collection.")
            boxes = []
            for detection in result.detections:
                box = detection.bounding_box
                converted = _box_to_frame(box.origin_x, box.origin_y, box.width, box.height, 
                                          small.shape[1], small.shape[0], width, height)
                if converted is not None:
                    boxes.append(converted)
        except (AttributeError, TypeError, ValueError, OverflowError) as error:
            raise ValueError("MediaPipe returned a malformed detection result.") from error
        return DetectionResult(person_count=len(boxes), bounding_boxes=tuple(boxes))

    def close(self) -> None:
        """Release native task resources after the sole detection worker stops."""
        if self._closed:
            return
        self._closed = True
        backend, self._backend = self._backend, None
        if backend is not None:
            backend.close()