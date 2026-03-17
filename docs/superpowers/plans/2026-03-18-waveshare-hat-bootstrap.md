# Waveshare e-ink HAT Bootstrap — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `hat/` package with Waveshare 2.7" e-ink driver + button handler, deploy scripts, and a standalone hello-world demo that shows text on e-ink and echoes KEY1-KEY4 presses.

**Architecture:** Thin `EinkDisplay` wrapper over the vendor Waveshare driver (selected by `EPD_VARIANT` constant); `ButtonHandler` using `gpiozero.Button` interrupt callbacks; `demo.py` ties both together with `threading.Lock` for display access. Deploy via `rsync`. No automated test framework exists — verification uses syntax checks locally and SSH hardware runs on RPi3.

**Tech Stack:** Python 3.11, Pillow 12, gpiozero 2, rpi-lgpio 0.6 (RPi.GPIO compat), Waveshare e-Paper driver (vendor copy), bash (deploy scripts). Target: RPi3 at `romano@10.0.0.47`, Raspberry OS Lite.

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `hat/__init__.py` | Create | Re-exports `EinkDisplay`, `ButtonHandler` |
| `hat/epd.py` | Create | `EinkDisplay` wrapper; `EPD_VARIANT` constant |
| `hat/buttons.py` | Create | `ButtonHandler` with gpiozero interrupt callbacks |
| `hat/vendor/__init__.py` | Create | Package marker for vendor drivers |
| `hat/vendor/epd2in7.py` | Download | Waveshare b&w driver (264×176) |
| `hat/vendor/epd2in7b.py` | Download | Waveshare tri-color driver (fallback) |
| `hat/vendor/epdconfig.py` | Download | Waveshare HAL (SPI + RPi.GPIO) |
| `hat/demo.py` | Create | Hello world + KEY1-KEY4 echo, standalone |
| `deploy/rsync.sh` | Create | rsync dev machine → RPi3 |
| `deploy/install-rpi.sh` | Create | Verify/install RPi deps |
| `requirements-rpi.txt` | Create | Document RPi-specific deps |

---

## Task 0: Stop conflicting services on RPi3

> **Note:** The Enviro+ HAT must be physically removed and the Waveshare HAT installed **after** this task. This task only stops the software — you still need to swap the hardware.

**Files:** none (SSH command only)

- [ ] **Step 1: Stop and disable the two Pimoroni services**

```bash
ssh romano@10.0.0.47 "sudo systemctl stop air_quality network_status && sudo systemctl disable air_quality network_status"
```

- [ ] **Step 2: Verify both services are no longer running**

```bash
ssh romano@10.0.0.47 "systemctl is-active air_quality network_status"
```

Expected output:
```
inactive
inactive
```

- [ ] **Step 3: Physically swap the HAT**

Remove Enviro+ HAT from GPIO header. Mount Waveshare 2.7" e-paper HAT. No software step — just a reminder checkpoint before continuing.

---

## Task 1: Deploy infrastructure

**Files:**
- Create: `deploy/rsync.sh`
- Create: `deploy/install-rpi.sh`
- Create: `requirements-rpi.txt`

- [ ] **Step 1: Create `deploy/rsync.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
REMOTE="romano@10.0.0.47"
REMOTE_PATH="~/powermeter-active-learner"
rsync -avz \
  --exclude='*.db' \
  --exclude='*.pt' \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.env' \
  . "${REMOTE}:${REMOTE_PATH}/"
echo "Rsync completato → ${REMOTE}:${REMOTE_PATH}"
```

- [ ] **Step 2: Create `deploy/install-rpi.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
declare -A PKGS=(
  ["spidev"]="spidev"
  ["Pillow"]="PIL"
  ["gpiozero"]="gpiozero"
  ["rpi-lgpio"]="lgpio"
)
for pypi_name in "${!PKGS[@]}"; do
  import_name="${PKGS[$pypi_name]}"
  python3 -c "import ${import_name}" 2>/dev/null \
    && echo "[OK] ${pypi_name}" \
    || { echo "[INSTALL] ${pypi_name}"; pip3 install --break-system-packages "${pypi_name}"; }
done
echo "Installazione completata."
```

- [ ] **Step 3: Create `requirements-rpi.txt`**

```
# Dipendenze specifiche Raspberry Pi (Raspberry OS Lite, Python 3.11)
# Nota: torch su ARM richiede URL speciale:
#   pip install torch --index-url https://download.pytorch.org/whl/cpu
numpy
# Le seguenti sono già pre-installate su questo RPi ma documentate per fresh setup:
spidev>=3.5
Pillow>=10.0
gpiozero>=2.0
rpi-lgpio>=0.6
```

- [ ] **Step 4: Make scripts executable and verify syntax**

```bash
chmod +x deploy/rsync.sh deploy/install-rpi.sh
bash -n deploy/rsync.sh && echo "rsync.sh syntax OK"
bash -n deploy/install-rpi.sh && echo "install-rpi.sh syntax OK"
```

Expected: both print `syntax OK`

- [ ] **Step 5: Commit**

```bash
git add deploy/ requirements-rpi.txt
git commit -m "feat: add deploy scripts and requirements-rpi.txt"
```

---

## Task 2: Waveshare vendor drivers

**Files:**
- Create: `hat/vendor/__init__.py`
- Download: `hat/vendor/epd2in7.py`
- Download: `hat/vendor/epd2in7b.py`
- Download: `hat/vendor/epdconfig.py`

Source: `https://github.com/waveshare/e-Paper`
Path in upstream repo: `RaspberryPi_JetsonNano/python/lib/waveshare_epd/`

- [ ] **Step 1: Create vendor package directory and marker**

```bash
mkdir -p hat/vendor
```

```python
# hat/vendor/__init__.py
# Waveshare vendor driver files — copied from:
# https://github.com/waveshare/e-Paper
# Path: RaspberryPi_JetsonNano/python/lib/waveshare_epd/
```

- [ ] **Step 2: Download the three driver files**

```bash
BASE="https://raw.githubusercontent.com/waveshare/e-Paper/master/RaspberryPi_JetsonNano/python/lib/waveshare_epd"
curl -fsSL "${BASE}/epd2in7.py"   -o hat/vendor/epd2in7.py
curl -fsSL "${BASE}/epd2in7b.py"  -o hat/vendor/epd2in7b.py
curl -fsSL "${BASE}/epdconfig.py" -o hat/vendor/epdconfig.py
```

- [ ] **Step 3: Verify files are non-empty and contain expected class**

```bash
grep -q "class EPD" hat/vendor/epd2in7.py  && echo "epd2in7.py OK"
grep -q "class EPD" hat/vendor/epd2in7b.py && echo "epd2in7b.py OK"
grep -q "class RaspberryPi" hat/vendor/epdconfig.py && echo "epdconfig.py OK"
```

Expected: all three print `OK`

- [ ] **Step 4: Syntax-check the downloaded files**

```bash
python3 -m py_compile hat/vendor/epd2in7.py   && echo "epd2in7 syntax OK"
python3 -m py_compile hat/vendor/epd2in7b.py  && echo "epd2in7b syntax OK"
python3 -m py_compile hat/vendor/epdconfig.py && echo "epdconfig syntax OK"
```

Expected: all three print `syntax OK` (imports of `RPi.GPIO`/`spidev` are NOT resolved here — that's fine, they only run on RPi)

- [ ] **Step 5: Commit**

```bash
git add hat/vendor/
git commit -m "feat: add Waveshare vendor drivers (epd2in7, epd2in7b, epdconfig)"
```

---

## Task 3: `hat/epd.py` — EinkDisplay

**Files:**
- Create: `hat/epd.py`

- [ ] **Step 1: Write `hat/epd.py`**

```python
#!/usr/bin/env python3
"""
hat/epd.py — EinkDisplay: thin wrapper around the Waveshare e-paper driver.

EPD_VARIANT selects which driver to load:
  "epd2in7"  — 2.7-inch black & white (264×176)  ← default
  "epd2in7b" — 2.7-inch tri-color B/W/Red (264×176)
"""
import importlib
from PIL import Image

# Change to "epd2in7b" if your HAT is the tri-color (B/W/Red) variant
EPD_VARIANT = "epd2in7"

WIDTH = 264
HEIGHT = 176


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
```

- [ ] **Step 2: Syntax-check on dev machine**

```bash
python3 -m py_compile hat/epd.py && echo "hat/epd.py syntax OK"
```

Expected: `hat/epd.py syntax OK`

- [ ] **Step 3: Verify importable with mocked vendor (dev machine)**

```bash
python3 - <<'EOF'
import sys
from unittest.mock import MagicMock
sys.modules['hat.vendor.epd2in7'] = MagicMock()
# Patch importlib.import_module so it returns the mock
import importlib
_real_import = importlib.import_module
def _mock_import(name, *a, **kw):
    if name == 'hat.vendor.epd2in7':
        return sys.modules['hat.vendor.epd2in7']
    return _real_import(name, *a, **kw)
importlib.import_module = _mock_import

from hat.epd import EinkDisplay
d = EinkDisplay()
print("EinkDisplay instantiation OK")
EOF
```

Expected: `EinkDisplay instantiation OK`

- [ ] **Step 4: Commit**

```bash
git add hat/epd.py
git commit -m "feat: add hat/epd.py EinkDisplay wrapper"
```

---

## Task 4: `hat/buttons.py` — ButtonHandler

**Files:**
- Create: `hat/buttons.py`

- [ ] **Step 1: Write `hat/buttons.py`**

```python
#!/usr/bin/env python3
"""
hat/buttons.py — ButtonHandler: GPIO interrupt handler for Waveshare KEY1-KEY4.

Uses gpiozero.Button with pull_up=True (Waveshare keys are active-low).
Callbacks are invoked in the gpiozero device manager thread (not main thread).
Call stop() to release GPIO resources before exiting.
"""
from typing import Callable

from gpiozero import Button

# Waveshare 2.7" HAT: key number → GPIO BCM pin
KEY_PINS: dict[int, int] = {1: 5, 2: 6, 3: 13, 4: 19}


class ButtonHandler:
    """
    Registers interrupt callbacks for KEY1-KEY4 on the Waveshare e-paper HAT.

    Buttons are active immediately on construction.
    Call stop() to release all GPIO resources.
    """

    def __init__(self, callbacks: dict[int, Callable[[], None]]) -> None:
        """
        Parameters
        ----------
        callbacks : dict[int, Callable]
            Mapping from key number (1-4) to zero-argument callable.
            Keys absent from the dict are monitored but trigger no callback.
        """
        self._buttons: list[Button] = []
        for key_num, gpio_pin in KEY_PINS.items():
            btn = Button(gpio_pin, pull_up=True)
            if key_num in callbacks:
                btn.when_pressed = callbacks[key_num]
            self._buttons.append(btn)

    def stop(self) -> None:
        """Release all GPIO resources. Must be called during cleanup."""
        for btn in self._buttons:
            btn.close()
        self._buttons.clear()
```

- [ ] **Step 2: Syntax-check on dev machine**

```bash
python3 -m py_compile hat/buttons.py && echo "hat/buttons.py syntax OK"
```

Expected: `hat/buttons.py syntax OK`

- [ ] **Step 3: Verify importable with mocked gpiozero (dev machine)**

```bash
python3 - <<'EOF'
import sys
from unittest.mock import MagicMock, patch

# Mock gpiozero.Button so it doesn't need real GPIO
mock_button = MagicMock()
mock_gpiozero = MagicMock()
mock_gpiozero.Button = mock_button
sys.modules['gpiozero'] = mock_gpiozero

from hat.buttons import ButtonHandler, KEY_PINS

assert KEY_PINS == {1: 5, 2: 6, 3: 13, 4: 19}, f"Wrong pins: {KEY_PINS}"

called = []
bh = ButtonHandler({1: lambda: called.append(1)})
bh.stop()
print("ButtonHandler instantiation OK")
print(f"KEY_PINS: {KEY_PINS}")
EOF
```

Expected:
```
ButtonHandler instantiation OK
KEY_PINS: {1: 5, 2: 6, 3: 13, 4: 19}
```

- [ ] **Step 4: Commit**

```bash
git add hat/buttons.py
git commit -m "feat: add hat/buttons.py ButtonHandler"
```

---

## Task 5: `hat/__init__.py`

**Files:**
- Create: `hat/__init__.py`

- [ ] **Step 1: Write `hat/__init__.py`**

```python
from hat.epd import EinkDisplay
from hat.buttons import ButtonHandler

__all__ = ["EinkDisplay", "ButtonHandler"]
```

- [ ] **Step 2: Verify package exports with mocks**

```bash
python3 - <<'EOF'
import sys
from unittest.mock import MagicMock
sys.modules['gpiozero'] = MagicMock()
sys.modules['hat.vendor.epd2in7'] = MagicMock()
import importlib
_real = importlib.import_module
importlib.import_module = lambda n, *a, **kw: sys.modules.get(n) or _real(n, *a, **kw)

import hat
assert hasattr(hat, 'EinkDisplay'), "EinkDisplay not exported"
assert hasattr(hat, 'ButtonHandler'), "ButtonHandler not exported"
print("hat package exports OK")
EOF
```

Expected: `hat package exports OK`

- [ ] **Step 3: Commit**

```bash
git add hat/__init__.py
git commit -m "feat: add hat/__init__.py package exports"
```

---

## Task 6: `hat/demo.py` — Hello World + button echo

**Files:**
- Create: `hat/demo.py`

- [ ] **Step 1: Write `hat/demo.py`**

```python
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
```

- [ ] **Step 2: Syntax-check on dev machine**

```bash
python3 -m py_compile hat/demo.py && echo "hat/demo.py syntax OK"
```

Expected: `hat/demo.py syntax OK`

- [ ] **Step 3: Commit**

```bash
git add hat/demo.py
git commit -m "feat: add hat/demo.py hello world + button echo"
```

---

## Task 7: Rsync to RPi and hardware verification

> **Prerequisite:** Waveshare 2.7" HAT is physically mounted on the RPi3 GPIO header (Task 0, Step 3).

**Files:** none new — deploy and verify

- [ ] **Step 1: Rsync repo to RPi**

```bash
./deploy/rsync.sh
```

Expected: rsync output listing transferred files, ending with `Rsync completato → romano@10.0.0.47:~/powermeter-active-learner`

- [ ] **Step 2: Verify RPi dependencies**

```bash
ssh romano@10.0.0.47 "cd ~/powermeter-active-learner && bash deploy/install-rpi.sh"
```

Expected: four `[OK]` lines (all deps already present on this RPi):
```
[OK] spidev
[OK] Pillow
[OK] gpiozero
[OK] rpi-lgpio
Installazione completata.
```

- [ ] **Step 3: Run demo on RPi**

```bash
ssh -t romano@10.0.0.47 "cd ~/powermeter-active-learner && python3 hat/demo.py"
```

Expected on stdout:
```
[BOOT] Hello World — 2026-03-18 HH:MM
In attesa di pressioni tasti (Ctrl-C per uscire)...
```

Expected on hardware: "Hello World" + date visible on e-ink display (~2s to refresh).

- [ ] **Step 4: Test each button**

With the SSH session open, physically press KEY1, KEY2, KEY3, KEY4 in sequence.

Expected stdout for each press:
```
[KEY1] pressed at HH:MM:SS
[KEY2] pressed at HH:MM:SS
[KEY3] pressed at HH:MM:SS
[KEY4] pressed at HH:MM:SS
```

Expected on hardware: display updates to show `KEY<N> premuto` + timestamp after each press.

- [ ] **Step 5: Test clean shutdown**

Press Ctrl-C in the SSH session.

Expected:
```
Shutdown — saving EPD state...
```

Expected on hardware: display retains last image (e-ink is non-volatile), EPD enters sleep mode.

- [ ] **Step 6: If display shows wrong colors (tri-color HAT)**

If display shows artifacts or unexpected colors instead of crisp black & white:
```bash
# Edit hat/epd.py line: EPD_VARIANT = "epd2in7b"
# Then re-deploy:
./deploy/rsync.sh
ssh -t romano@10.0.0.47 "cd ~/powermeter-active-learner && python3 hat/demo.py"
```

- [ ] **Step 7: Final commit**

```bash
git add -A
git commit -m "feat: waveshare e-ink HAT bootstrap complete — hello world + button echo"
```

---

## Summary of success criteria

- [ ] `air_quality.service` and `network_status.service` stopped and disabled
- [ ] `hat/vendor/` contains `epd2in7.py`, `epd2in7b.py`, `epdconfig.py`
- [ ] `hat/epd.py`, `hat/buttons.py`, `hat/demo.py` pass syntax checks locally
- [ ] `hat/demo.py` shows "Hello World" on e-ink display on first run
- [ ] KEY1-KEY4 each update the display and log to stdout
- [ ] Ctrl-C exits cleanly with EPD sleep
- [ ] Repo organized with `hat/` and `deploy/` separate from `engine/`
