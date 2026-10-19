import tkinter as tk
from typing import Callable

from red_handed.detection.privacy_zone import PrivacyZone


class ZonePreview(tk.Canvas):
    """Camera preview canvas where the user drags out a privacy zone.

    * The parent window pushes frames in via show_image() (a Tk PhotoImage).
    * When `editing` is True, the user can click-and-drag on the image to draw
      a rectangle. That rectangle is the *draft* zone (unsaved, dashed yellow).
    * When the mouse is released, `on_draft` is called so the parent can react
      (e.g. enable a "Save zone" button). The parent decides whether to save it
      by copying draft_zone into saved_zone, or to throw it away with
      discard_draft().
    * The *saved* zone (solid blue) is whatever the parent last stored in
      `saved_zone`.

    Coordinate convention
    ---------------------
    Zones are stored in NORMALISED coordinates (0.0 to 1.0 across the image),
    not pixels. This means a zone stays valid even if the displayed image or
    the canvas is resized. Pixels are only computed at draw time.
    """

    def __init__(self, parent, on_draft: Callable[[], None]) -> None:
        super().__init__(parent, width=640, height=320, bg="black", highlightthickness=0)

        # zone state (public: the parent reads/writes these)
        self.saved_zone: PrivacyZone | None = None  # the zone currently in effect
        self.draft_zone: PrivacyZone | None = None  # the zone being drawn, not yet saved
        self.editing: bool = False                  # True = user may draw a zone

        # internal state (single underscore = private by convention)
        # (self.__x -> self._ZonePreview__x), which breaks access if the name
        # is written inconsistently elsewhere.
        self._photo = None                          # current PhotoImage; must be kept
                                                    # referenced or Tk garbage-collects it
        self._start: tuple[float, float] | None = None  # where the drag began (normalised)
        self._on_draft = on_draft                   # callback fired when a drag finishes
        self._message = "Camera preview is inactive. Please select a camera to see the preview."

        # event bindings 
        # Redraw whenever the canvas is resized so the image stays centred.
        self.bind("<Configure>", lambda _event: self._draw())
        # The three mouse events that make up one rectangle-drawing gesture.
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", self._release)

    # ------------------------------------------------------------------
    # Public API (called by the parent window)
    # ------------------------------------------------------------------

    def show_image(self, photo) -> None:
        """Display a new camera frame (a tk.PhotoImage)."""
        self._photo = photo  # store the reference, otherwise the image disappears
        self._draw()

    def clear(self, text: str) -> None:
        """Remove the image and show a text message instead (e.g. camera off)."""
        self._photo = None
        self._message = text
        self.discard_draft()  # also redraws, so the message appears immediately

    def set_editing(self, enabled: bool) -> None:
        """Turn zone drawing on or off. Always drops any half-finished draft."""
        self.editing = enabled
        self.configure(cursor="crosshair" if enabled else "")
        self.discard_draft()

    def discard_draft(self) -> None:
        """Throw away the unsaved zone and any in-progress drag."""
        self.draft_zone = None
        self._start = None
        self._draw()

    # ------------------------------------------------------------------
    # Coordinate translation
    # ------------------------------------------------------------------

    def _point(self, x: float, y: float, clamp: bool = False) -> tuple[float, float] | None:
        """Convert a canvas pixel (x, y) into a normalised image coordinate.

        The image is drawn centred in the canvas, so the canvas has an empty
        margin around it. We subtract that margin (left/top) and divide by the
        image size to get 0..1 values relative to the image itself.

        clamp=False: return None if the point is outside the image
                     (used when a drag STARTS - must begin on the image).
        clamp=True:  squash the point onto the image edge instead
                     (used while dragging - the rectangle stops at the border
                     even if the mouse wanders off the image).
        """
        if self._photo is None:
            return None  # no image yet, nothing to map onto
        width, height = self._photo.width(), self._photo.height()
        left = (self.winfo_width() - width) / 2   # empty margin left of image
        top = (self.winfo_height() - height) / 2  # empty margin above image
        nx, ny = (x - left) / width, (y - top) / height
        if clamp:
            return max(0.0, min(1.0, nx)), max(0.0, min(1.0, ny))
        # Parentheses matter: without them this parses as nx, (ny if ... else None)
        return (nx, ny) if 0 <= nx <= 1 and 0 <= ny <= 1 else None

    # ------------------------------------------------------------------
    # Mouse handlers: press -> drag (many times) -> release
    # ------------------------------------------------------------------

    def _press(self, event) -> None:
        """Mouse button down: begin a new rectangle at this point."""
        if not self.editing:
            return
        self.draft_zone = None  # a new drag replaces any previous unsaved draft
        # Stays None if the click landed outside the image, which makes the
        # following drag/release do nothing.
        self._start = self._point(event.x, event.y)
        self._draw()

    def _drag(self, event) -> None:
        """Mouse moved with button held: update the draft rectangle live."""
        if not self.editing or self._start is None:
            return  # not editing, or the press started outside the image
        end = self._point(event.x, event.y, clamp=True)
        if end is None:
            return
        try:
            # (start corner, current corner, 1, 1): the 1, 1 are the "image
            # width/height" because our coordinates are already normalised.
            self.draft_zone = PrivacyZone.from_pixels(*self._start, *end, 1, 1)
        except ValueError:
            # PrivacyZone rejects invalid shapes (e.g. zero area when the
            # mouse is still on the start point), so show no draft for now.
            self.draft_zone = None
        self._draw()

    def _release(self, event) -> None:
        """Mouse button up: finalise the draft and tell the parent about it."""
        self._drag(event)   # apply the final mouse position
        self._start = None  # the drag gesture is over
        if self.draft_zone is not None:
            # Only notify if a valid rectangle exists. A plain click (no drag)
            # or a press outside the image leaves draft_zone as None.
            self._on_draft()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _draw(self) -> None:
        """Redraw everything from scratch. Cheap enough to call on every event."""
        self.delete("all")
        cx, cy = self.winfo_width() / 2, self.winfo_height() / 2  # canvas centre

        # No image: show the status message and stop.
        if self._photo is None:
            self.create_text(cx, cy, text=self._message, fill="#e5e7eb")
            return

        # Images are placed by their centre by default, so this centres it.
        self.create_image(cx, cy, image=self._photo)

        # Zones are only visible while editing.
        if not self.editing:
            return

        width, height = self._photo.width(), self._photo.height()
        # Top-left corner of the image on the canvas; zone pixel positions
        # are relative to the image, so we add this offset to each one.
        left, top = cx - width / 2, cy - height / 2

        # (zone, outline colour, dash pattern, label text)
        # Saved = solid blue, Draft = dashed yellow, so they are easy to tell apart.
        for zone, color, dash, label in [
            (self.saved_zone, "#60a5fa", (), "Saved zone"),
            (self.draft_zone, "#fbbf24", (5, 3), "Unsaved zone"),
        ]:
            if zone is None:
                continue
            # Normalised zone -> pixel rectangle within the image.
            x1, y1, x2, y2 = zone.to_pixels(width, height)
            self.create_rectangle(left + x1, top + y1, left + x2, top + y2,
                                  outline=color, dash=dash, width=2, tags="zone")
            # Small label tucked inside the rectangle's top-left corner.
            self.create_text(left + x1 + 4, top + y1 + 4, text=label,
                             anchor="nw", fill=color, tags="zone")