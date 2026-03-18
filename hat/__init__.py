"""
hat — Waveshare 2.7-inch e-paper HAT interface.

WARNING: This package can only be imported on Raspberry Pi hardware (or with
the hat.vendor modules mocked), because hat/vendor/epdconfig.py runs hardware
detection code (subprocess + GPIO init) at module-load time.

For dev-machine testing, mock hat.vendor.epd2in7_V2 before importing:
    sys.modules['hat.vendor.epd2in7_V2'] = MagicMock()
"""
from hat.epd import EinkDisplay, WIDTH, HEIGHT, LANDSCAPE_W, LANDSCAPE_H
from hat.buttons import ButtonHandler
from hat.ui import UIState, DebugState, render_frame, render_debug_frame

__all__ = [
    "EinkDisplay", "ButtonHandler",
    "UIState", "DebugState", "render_frame", "render_debug_frame",
    "WIDTH", "HEIGHT", "LANDSCAPE_W", "LANDSCAPE_H",
]
