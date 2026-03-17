# Design Spec — Waveshare e-ink HAT Bootstrap

**Date:** 2026-03-18
**Scope:** Sessione 1 — struttura repo, pulizia RPi, hello world + test tasti
**Out of scope:** Integrazione RL feedback / UI schermate operative (sessione futura)

---

## Contesto

Il progetto `powermeter-active-learner` gira su un RPi3 (`romano@10.0.0.47`, Raspberry OS Lite).
È stato aggiunto un display **Waveshare 2.7inch e-paper HAT** (264×176 px, b&w, 4 tasti programmabili KEY1-KEY4).

Il RPi ha attualmente due servizi attivi che usano l'Enviro+ HAT (ST7735 display + sensori Pimoroni):
- `air_quality.service` → `/home/romano/air_quality.py`
- `network_status.service` → `/home/romano/network_status.py`

Entrambi devono essere fermati e disabilitati prima di collegare il Waveshare HAT.

### Stato hardware RPi (verificato via SSH)

- Python 3.11.2
- SPI abilitato: `/dev/spidev0.0` e `/dev/spidev0.1` presenti
- Dipendenze già installate: `spidev 3.5`, `Pillow 12.1.1`, `gpiozero 2.0.1`, `rpi-lgpio 0.6`
- `rpi-lgpio` fornisce compatibilità `RPi.GPIO` — i driver Waveshare ufficiali funzionano senza modifiche

### Pin Waveshare 2.7" HAT (standard)

| Funzione | GPIO BCM |
|----------|----------|
| KEY1     | 5        |
| KEY2     | 6        |
| KEY3     | 13       |
| KEY4     | 19       |
| BUSY     | 24       |
| RST      | 17       |
| DC       | 25       |
| CS       | 8 (SPI0.0) |

---

## Struttura repo target

```
powermeter-active-learner/
├── engine/              # ML/NILM core — invariato
│   └── ...
├── hat/                 # Waveshare HAT interface
│   ├── __init__.py      # esporta: EinkDisplay, ButtonHandler
│   ├── epd.py           # EinkDisplay: wrapper su driver Waveshare
│   ├── buttons.py       # ButtonHandler: GPIO interrupt-based KEY1-KEY4
│   ├── vendor/          # Driver ufficiali Waveshare (copiati, non submodule)
│   │   ├── epd2in7.py   # driver 2.7" b&w
│   │   ├── epd2in7b.py  # driver 2.7" tri-color (b&w&rosso) — copiato preventivamente
│   │   └── epdconfig.py # HAL SPI/GPIO (condiviso da entrambi i driver)
│   └── demo.py          # Standalone: hello world + echo tasti (entry point sessione 1)
├── deploy/
│   ├── rsync.sh         # rsync dal dev machine al RPi
│   └── install-rpi.sh   # verifica e installa dipendenze sul RPi
├── docs/
│   └── superpowers/specs/
│       └── 2026-03-18-waveshare-hat-bootstrap-design.md
├── main.py              # invariato (usa ancora MockDataSource)
├── requirements.txt     # dipendenze standard (torch, numpy)
└── requirements-rpi.txt # dipendenze specifiche RPi
```

---

## Componenti

### `hat/vendor/` — driver Waveshare

Sorgente: `https://github.com/waveshare/e-Paper` (branch `master`).
Path nel repo upstream: `RaspberryPi_JetsonNano/python/lib/waveshare_epd/`

File da copiare:
- `epd2in7.py` — driver b&w 264×176; classe `EPD` con metodi `init()`, `Clear()`, `display(image_buf)`, `sleep()`
- `epd2in7b.py` — driver tri-color; stessa interfaccia ma `display(imageblack, imagered)`
- `epdconfig.py` — HAL SPI/GPIO condiviso; usa `RPi.GPIO` (soddisfatto da `rpi-lgpio 0.6`)

Entrambi i driver vengono copiati preventivamente: l'implementazione usa `epd2in7` di default,
con possibilità di switch via costante in `hat/epd.py`.

### `hat/__init__.py`

```python
from hat.epd import EinkDisplay
from hat.buttons import ButtonHandler

__all__ = ["EinkDisplay", "ButtonHandler"]
```

### `hat/epd.py` — `EinkDisplay`

Thin wrapper su driver Waveshare. La variante driver è selezionata da una costante di modulo:

```python
# Cambiare in "epd2in7b" se l'HAT è la variante tri-color
EPD_VARIANT = "epd2in7"
```

L'import avviene a runtime in base al valore di `EPD_VARIANT`:
```python
import importlib
_epd_module = importlib.import_module(f"hat.vendor.{EPD_VARIANT}")
_EPD_CLASS = _epd_module.EPD
```

Interfaccia pubblica:
```python
class EinkDisplay:
    def __init__(self) -> None
        # Crea istanza EPD interna; non chiama init() — chiamare init() esplicitamente
    def init(self) -> None
        # Chiama epd.init(); necessario dopo ogni power-on e dopo sleep()
    def clear(self) -> None
        # Chiama epd.Clear(); richiede init() già chiamato
    def show_image(self, image: PIL.Image.Image) -> None
        # Converte Image in buffer bytes e chiama epd.display()
        # Per epd2in7: image deve essere mode "1" (1-bit), size (264, 176)
        # Per epd2in7b: lancia NotImplementedError (variante non usata nella demo)
    def sleep(self) -> None
        # Chiama epd.sleep(); mette il display in low-power mode
```

`show_image()` converte automaticamente l'immagine Pillow in `mode="1"` e la ridimensiona
a `(264, 176)` se necessario prima di passarla al driver.

### `hat/buttons.py` — `ButtonHandler`

```python
from gpiozero import Button
from typing import Callable

KEY_PINS: dict[int, int] = {1: 5, 2: 6, 3: 13, 4: 19}  # key_num → GPIO BCM

class ButtonHandler:
    def __init__(self, callbacks: dict[int, Callable[[], None]]) -> None
        # callbacks: {1: fn, 2: fn, 3: fn, 4: fn}
        # Crea Button gpiozero in __init__; assegna when_pressed
        # I Button usano pull_up=True (tasti Waveshare sono active-low)
    def stop(self) -> None
        # Chiama .close() su tutti i Button gpiozero — libera GPIO
```

- Non esiste `start()`: i Button gpiozero sono attivi dal momento della creazione.
- I callback vengono invocati nel thread del device manager gpiozero (thread separato dal main).
- `stop()` deve essere chiamato nel blocco `finally` o all'handler SIGINT.

### `hat/demo.py` — Hello World standalone

Script eseguibile: `python3 hat/demo.py` (dalla root del progetto)
Aggiunge `sys.path.insert(0, str(Path(__file__).parent.parent))` per risolvere `hat.*`.

**Font**: usa `PIL.ImageFont.load_default()` (sempre disponibile, nessuna dipendenza esterna).
Per testo più leggibile, tenta `ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)`
con fallback a `load_default()` se il file non esiste.

**Thread safety**: un `threading.Lock` (`_display_lock`) protegge le chiamate a `EinkDisplay.show_image()`.
Tutti gli aggiornamenti display (boot + callback tasti) acquisiscono il lock prima di disegnare.

**Flusso**:
1. Crea `EinkDisplay`, chiama `init()`, poi `clear()`
2. Disegna immagine "Hello World\n<timestamp>" e chiama `show_image()`
3. Crea `ButtonHandler` con callback per KEY1-KEY4; ogni callback:
   - acquisisce `_display_lock`
   - disegna immagine "KEY<N> premuto\n<timestamp>"
   - chiama `show_image()`
   - rilascia lock
   - stampa `[KEY<N>] pressed` su stdout
4. Loop principale: `signal.pause()` (blocca main thread, aspetta segnali)
5. SIGINT handler: chiama `button_handler.stop()`, `display.sleep()`, poi `sys.exit(0)`

### `deploy/rsync.sh`

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

### `deploy/install-rpi.sh`

Verifica che le dipendenze necessarie siano presenti sul RPi e installa quelle mancanti.

```bash
#!/usr/bin/env bash
set -euo pipefail
# Array associativo: PyPI package name → Python import name
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

### `requirements-rpi.txt`

```
# Dipendenze specifiche Raspberry Pi (Raspberry OS Lite, Python 3.11)
# Nota: torch su ARM richiede URL speciale:
#   pip install torch --index-url https://download.pytorch.org/whl/cpu
numpy
# Le seguenti sono già pre-installate su questo RPi ma documentate per setup fresh:
spidev>=3.5
Pillow>=10.0
gpiozero>=2.0
rpi-lgpio>=0.6   # fornisce RPi.GPIO compatibility layer
```

---

## Procedura di deploy sessione 1

1. **Fermare e disabilitare servizi** (da dev machine via SSH):
   ```bash
   ssh romano@10.0.0.47 "sudo systemctl stop air_quality network_status && sudo systemctl disable air_quality network_status"
   ```
2. **Fisicamente**: rimuovere Enviro+ HAT, montare Waveshare 2.7" HAT sul GPIO header del RPi3
3. **Rsync** del repo sul RPi (dalla root del repo su dev machine):
   ```bash
   chmod +x deploy/rsync.sh && ./deploy/rsync.sh
   ```
4. **Verificare dipendenze** (opzionale su questo RPi, tutto già presente):
   ```bash
   ssh romano@10.0.0.47 "cd ~/powermeter-active-learner && bash deploy/install-rpi.sh"
   ```
5. **Eseguire demo**:
   ```bash
   ssh romano@10.0.0.47 "cd ~/powermeter-active-learner && python3 hat/demo.py"
   ```
6. **Verificare**: "Hello World" visibile sul display; premere KEY1-KEY4 e verificare aggiornamento display + log stdout

**Se il display mostra artefatti o colori inattesi** (HAT variante tri-color):
- Aprire `hat/epd.py` e cambiare `EPD_VARIANT = "epd2in7b"`
- Ri-eseguire rsync + demo

---

## Criteri di successo sessione 1

- [ ] `air_quality.service` e `network_status.service` fermati e disabilitati
- [ ] `hat/demo.py` mostra "Hello World" su display e-ink al primo avvio
- [ ] Ogni pressione KEY1-KEY4 aggiorna il display con il numero del tasto premuto
- [ ] Nessun errore GPIO/SPI a runtime
- [ ] Il repo è organizzato con `hat/` e `deploy/` separati da `engine/`
- [ ] `hat/vendor/` contiene entrambi i driver (`epd2in7.py` e `epd2in7b.py`)

---

## Note e rischi

- **Modello driver**: si parte con `EPD_VARIANT = "epd2in7"` (b&w). Se l'HAT è tri-color, cambiare in `"epd2in7b"` — un valore costante in `hat/epd.py` è sufficiente per questa sessione.
- **Tempi di refresh e-ink**: il display 2.7" impiega ~2s per un refresh completo. Per la demo non è un problema; per l'UI futura si dovrà usare il partial refresh dove supportato dal modello.
- **Thread gpiozero**: i callback tasti girano in thread separati — il `threading.Lock` in `demo.py` è sufficiente per questa sessione. Per l'integrazione futura con il training loop si userà una coda thread-safe (`queue.Queue`).
- **Servizi Pimoroni**: i file `air_quality.py` e `network_status.py` vengono lasciati intatti su disco (solo i servizi disabilitati). Non interferiscono con il Waveshare HAT.
- **`signal.pause()`**: funziona su Linux (RPi OS Lite). Non è portabile su Windows, ma non è un requisito.
