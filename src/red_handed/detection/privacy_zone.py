"""FR3: normalized rectangular zones and frame-level face geometry."""

from dataclasses import dataclass
from math import isfinite

FaceBox = tuple[int, int, int, int]


def split_primary_face(boxes: tuple[FaceBox, ...]) -> tuple[FaceBox | None, tuple[FaceBox, ...]]:
    """Largest area is primary; equal areas use input order. No identity matching."""
    if not boxes:
        return None, ()
    index = max(range(len(boxes)), key=lambda i: boxes[i][2] * boxes[i][3])
    return boxes[index], boxes[:index] + boxes[index + 1:]


@dataclass(frozen=True)
class PrivacyZone:
    """Positive rectangle within [0, 1]; boundary points count as inside."""

    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        values = (self.x, self.y, self.width, self.height)
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v)
               for v in values):
            raise ValueError("Zone coordinates must be finite numbers.")
        if not (0 <= self.x < 1 and 0 <= self.y < 1 and
                0 < self.width <= 1 - self.x and 0 < self.height <= 1 - self.y):
            raise ValueError("The zone must have positive size and fit inside the frame.")

    def contains_point(self, x: float, y: float) -> bool:
        return self.x <= x <= self.x + self.width and self.y <= y <= self.y + self.height

    def to_pixels(self, frame_width: int, frame_height: int) -> tuple[float, float, float, float]:
        """Convert to (left, top, right, bottom) coordinates for rendering."""
        if frame_width <= 0 or frame_height <= 0:
            raise ValueError("Frame dimensions must be positive.")
        return (self.x * frame_width, self.y * frame_height,
                (self.x + self.width) * frame_width, (self.y + self.height) * frame_height)

    @classmethod
    def from_pixels(cls, x1: float, y1: float, x2: float, y2: float,
                    frame_width: int, frame_height: int) -> "PrivacyZone":
        if frame_width <= 0 or frame_height <= 0:
            raise ValueError("Frame dimensions must be positive.")
        left, right = sorted((x1 / frame_width, x2 / frame_width))
        top, bottom = sorted((y1 / frame_height, y2 / frame_height))
        return cls(left, top, right - left, bottom - top)

    # FR3.4: only the center of an additional face determines zone membership.
    def contains_face(self, box: FaceBox, frame_width: int, frame_height: int) -> bool:
        if frame_width <= 0 or frame_height <= 0:
            raise ValueError("Frame dimensions must be positive.")
        x, y, width, height = box
        if width <= 0 or height <= 0:
            raise ValueError("Face dimensions must be positive.")
        return self.contains_point((x + width / 2) / frame_width,
                                   (y + height / 2) / frame_height)