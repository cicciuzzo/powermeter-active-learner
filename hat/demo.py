#!/usr/bin/env python3
"""
hat/demo.py — Standalone hello world + button echo for Waveshare 2.7" HAT.

Run from project root:
    python3 hat/demo.py

Press KEY1-KEY4 to update the e-ink display with the key number.
Ctrl-C for clean exit (EPD goes to sleep).
"""
import signal
import sys
import threading
from datetime import datetime
from pathlib import Path

# Ensure project root is on sys.path when running as a script
sys.path.insert(0, str(Path(__file__).parent.parent))

from PIL import Image, ImageDraw, ImageFont

from hat.epd import EinkDisplay, WIDTH, HEIGHT
from hat.buttons import ButtonHandler

# --- Font setup ---
_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
try:
    FONT_LARGE = ImageFont.truetype(_FONT_PATH, 22)
    FONT_SMALL = ImageFont.truetype(_FONT_PATH, 14)
except OSError:
    FONT_LARGE = ImageFont.load_default()
    FONT_SMALL = ImageFont.load_default()

# Protects all EPD draw calls — gpiozero callbacks run in a separate thread
_display_lock = threading.Lock()


def _make_image(line1: str, line2: str = "") -> Image.Image:
    """Create a white 264×176 bitmap with up to two lines of text."""
    img = Image.new("1", (WIDTH, HEIGHT), 255)  # 255 = white in 1-bit mode
    draw = ImageDraw.Draw(img)
    draw.text((8, 20), line1, font=FONT_LARGE, fill=0)
    if line2:
        draw.text((8, 60), line2, font=FONT_SMALL, fill=0)
    return img


def _update_display(display: EinkDisplay, line1: str, line2: str = "") -> None:
    """Thread-safe display update."""
    with _display_lock:
        display.show_image(_make_image(line1, line2))


def main() -> None:
    display = EinkDisplay()
    display.init()
    display.clear()

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    _update_display(display, "Hello World", now)
    print(f"[BOOT] Hello World — {now}")

    def make_key_callback(key_num: int):
        def _cb():
            ts = datetime.now().strftime("%H:%M:%S")
            print(f"[KEY{key_num}] pressed at {ts}")
            _update_display(display, f"KEY{key_num} premuto", ts)
        return _cb

    buttons = ButtonHandler({k: make_key_callback(k) for k in range(1, 5)})
    print("In attesa di pressioni tasti (Ctrl-C per uscire)...")

    def _shutdown(sig, frame):
        print("\nShutdown — saving EPD state...")
        buttons.stop()
        display.sleep()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.pause()  # block main thread; gpiozero callbacks handle key events


if __name__ == "__main__":
    main()
