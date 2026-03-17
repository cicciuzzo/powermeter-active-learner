#!/usr/bin/env python3
"""
hat/epd.py — EinkDisplay: thin wrapper around the Waveshare e-paper driver.

EPD_VARIANT selects which driver to load:
  "epd2in7"  — 2.7-inch black & white (176×264 portrait)  ← default
  "epd2in7b" — 2.7-inch tri-color B/W/Red (176×264 portrait)
"""
import importlib
from PIL import Image

# Change to "epd2in7b" if your HAT is the tri-color (B/W/Red) variant
EPD_VARIANT = "epd2in7"

WIDTH = 176
HEIGHT = 264


def _load_driver():
    return importlib.import_module(f"hat.vendor.{EPD_VARIANT}")


class EinkDisplay:
    """Thin wrapper around the Waveshare EPD driver."""

    def __init__(self) -> None:
        mod = _load_driver()
        self._epd = mod.EPD()

    def init(self) -> None:
        """Initialise the display. Call before the first draw and after sleep()."""
        self._epd.init()

    def clear(self) -> None:
        """Fill the display with white. Requires init() first."""
        self._epd.Clear()

    def show_image(self, image: Image.Image) -> None:
        """
        Render a Pillow Image on the display.

        Auto-converts to mode "1" (1-bit B/W) and resizes to (WIDTH, HEIGHT)
        if needed. Requires init() to have been called.
        """
        if image.size != (WIDTH, HEIGHT):
            image = image.resize((WIDTH, HEIGHT))
        if image.mode != "1":
            image = image.convert("1")
        buf = self._epd.getbuffer(image)
        self._epd.display(buf)

    def sleep(self) -> None:
        """Put the display into low-power sleep mode."""
        self._epd.sleep()
