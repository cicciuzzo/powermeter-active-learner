#!/usr/bin/env python3
"""
hat/epd.py — EinkDisplay: thin wrapper around the Waveshare e-paper driver.

EPD_VARIANT selects which driver to load:
  "epd2in7"    — 2.7-inch black & white (176×264 portrait)
  "epd2in7_V2" — 2.7-inch black & white V2 hardware revision  ← default
  "epd2in7b"   — 2.7-inch tri-color B/W/Red (176×264 portrait)

Landscape support: the HAT is physically rotated 90° CCW (buttons on the left).
Callers render on a 264×176 landscape canvas; show_image() rotates it 90° CCW
back to the 176×264 portrait orientation expected by the driver.

Refresh strategy:
  - Fast refresh (no flash) for most updates via display_Fast()
  - Full refresh every FULL_REFRESH_INTERVAL frames to clear ghosting
  - First frame always uses full refresh to establish base image
"""
import importlib
import random
from PIL import Image

# Change to "epd2in7" for V1 hardware, or "epd2in7b" for tri-color variant
EPD_VARIANT = "epd2in7_V2"

WIDTH = 176
HEIGHT = 264

# Landscape dimensions (after 90 CCW physical rotation — buttons on left)
LANDSCAPE_W = HEIGHT  # 264
LANDSCAPE_H = WIDTH   # 176

# Anti-burn-in: random shift range in pixels
_SHIFT_MAX = 2

# Full refresh every N frames to clear ghosting (N * 15s = interval)
FULL_REFRESH_INTERVAL = 40  # ~10 minutes


def _load_driver():
    return importlib.import_module(f"hat.vendor.{EPD_VARIANT}")


class EinkDisplay:
    """Thin wrapper around the Waveshare EPD driver."""

    def __init__(self) -> None:
        mod = _load_driver()
        self._epd = mod.EPD()
        self._frame_count = 0
        self._fast_mode = False

    def init(self) -> None:
        """Initialise the display. Call before the first draw and after sleep()."""
        self._epd.init()
        self._fast_mode = False

    def _init_fast(self) -> None:
        """Switch to fast refresh mode (no flash)."""
        self._epd.init_Fast()
        self._fast_mode = True

    def clear(self) -> None:
        """Fill the display with white. Requires init() first."""
        self._epd.Clear()
        self._frame_count = 0

    @staticmethod
    def apply_burn_in_shift(image: Image.Image) -> Image.Image:
        """
        Apply random +/-2px shift to prevent e-ink burn-in.

        Draws content on a slightly oversized canvas, then crops at random offset.
        """
        w, h = image.size
        margin = _SHIFT_MAX * 2
        padded = Image.new("1", (w + margin, h + margin), 255)
        padded.paste(image, (_SHIFT_MAX, _SHIFT_MAX))
        ox = random.randint(0, margin)
        oy = random.randint(0, margin)
        return padded.crop((ox, oy, ox + w, oy + h))

    def _prepare_image(self, image: Image.Image) -> Image.Image:
        """Apply burn-in shift, rotation, resize, and mode conversion."""
        image = self.apply_burn_in_shift(image)
        if image.size == (LANDSCAPE_W, LANDSCAPE_H):
            image = image.transpose(Image.Transpose.ROTATE_90)
        if image.size != (WIDTH, HEIGHT):
            image = image.resize((WIDTH, HEIGHT))
        if image.mode != "1":
            image = image.convert("1")
        return image

    def show_image(self, image: Image.Image) -> None:
        """
        Render a Pillow Image on the display.

        Uses fast refresh (no flash) for most frames. Every
        FULL_REFRESH_INTERVAL frames, does a full refresh to clear ghosting.
        The first frame always uses full refresh to establish a clean base.
        """
        image = self._prepare_image(image)
        buf = self._epd.getbuffer(image)

        if self._frame_count % FULL_REFRESH_INTERVAL == 0:
            # Full refresh: re-init in normal mode, display with flash
            if self._fast_mode:
                self._epd.init()
                self._fast_mode = False
            self._epd.display(buf)
        else:
            # Fast refresh: no flash
            if not self._fast_mode:
                self._init_fast()
            self._epd.display_Fast(buf)

        self._frame_count += 1

    def sleep(self) -> None:
        """Put the display into low-power sleep mode."""
        self._epd.sleep()
