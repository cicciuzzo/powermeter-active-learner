"""
hat — Waveshare 2.7-inch e-paper HAT interface.

WARNING: This package can only be imported on Raspberry Pi hardware (or with
the hat.vendor modules mocked), because hat/vendor/epdconfig.py runs hardware
detection code (subprocess + GPIO init) at module-load time.

For dev-machine testing, mock hat.vendor.epd2in7 before importing:
    sys.modules['hat.vendor.epd2in7'] = MagicMock()
"""
from hat.epd import EinkDisplay
from hat.buttons import ButtonHandler

__all__ = ["EinkDisplay", "ButtonHandler"]
