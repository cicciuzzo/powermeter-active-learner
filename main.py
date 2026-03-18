#!/usr/bin/env python3
"""
main.py — Entry point for the powermeter-active-learner system.

Runs a continuous loop (15-second ticks) that:
  1. Reads current power consumption (W) from a DataSource.
  2. Accumulates readings in a SignalWindow.
  3. Once the window is full, classifies the state via:
       - Idle gate (trivial IDLE) when max(window) < IDLE_GATE_W
       - BaselineDetector during cold-start (insufficient class diversity)
       - PowerNet (1D-CNN) after sufficient labeled data has been collected.
  4. Feeds the raw reading to the DriftDetector.
  5. Manages labeling events and triggers incremental training when possible.
  6. Prints a human-readable status line to stdout.

Graceful Ctrl-C saves the model checkpoint before exiting.
"""

import json
import os
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

# Load .env file if present (stdlib-only, no python-dotenv)
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.isfile(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _, _val = _line.partition("=")
                os.environ.setdefault(_key.strip(), _val.strip())

from engine import IDLE, WASHER, DRYER, BOTH, STATE_NAMES
from engine.data_source import MockDataSource
from engine.signal_pipeline import SignalWindow, BaselineDetector, MultiScaleWindow
from engine.replay_buffer import ReplayBuffer
from engine.label_manager import LabelManager
from engine.confidence import ConfidenceTracker, DriftDetector, confidence_blend

# HAT display (RPi-only — skip on dev machines)
try:
    from hat import EinkDisplay, ButtonHandler, UIState, DebugState, render_frame, render_debug_frame, render_standby_frame
    _HAT_AVAILABLE = True
except ImportError:
    _HAT_AVAILABLE = False

# Home Assistant data source
from engine.ha_source import HomeAssistantDataSource

try:
    from engine.model import PowerNet
    from engine.trainer import Trainer
    _TORCH_AVAILABLE = True
except ImportError as _torch_err:
    _TORCH_AVAILABLE = False
    _TORCH_IMPORT_ERROR = str(_torch_err)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TICK_INTERVAL = 15          # seconds between power readings
DEFAULT_BATCH_SIZE = 32

# Smart cold start: CNN activates when enough non-idle class diversity exists
COLD_START_CLASS_MIN = 5        # min samples per non-idle class
COLD_START_CLASSES_REQUIRED = 2 # min non-idle classes meeting the threshold

# If max wattage in window is below this, skip CNN and use BaselineDetector
IDLE_GATE_W = 15.0

# Class weights: IDLE is ~70 % of real-world time, so up-weight rare classes
CLASS_WEIGHTS = [0.3, 1.5, 1.5, 2.0]   # [IDLE, WASHER, DRYER, BOTH]

# Set to True to use Home Assistant; False to use MockDataSource
USE_HA_SOURCE = bool(os.environ.get("HA_URL"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_cpu_percent() -> float:
    """Read normalized CPU load (0-100) from /proc/loadavg."""
    try:
        with open("/proc/loadavg") as f:
            load_1min = float(f.read().split()[0])
        ncpu = os.cpu_count() or 1
        return min(load_1min / ncpu * 100, 100.0)
    except (OSError, ValueError):
        return 0.0


def _read_temperature() -> float:
    """Read CPU temperature from thermal zone."""
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return int(f.read().strip()) / 1000.0
    except (OSError, ValueError):
        return 0.0


def _read_ram_free() -> float:
    """Read free RAM percentage from /proc/meminfo."""
    try:
        with open("/proc/meminfo") as f:
            lines = f.readlines()
        total = avail = 0
        for line in lines:
            if line.startswith("MemTotal:"):
                total = int(line.split()[1])
            elif line.startswith("MemAvailable:"):
                avail = int(line.split()[1])
        return (avail / total * 100) if total > 0 else 0.0
    except (OSError, ValueError, ZeroDivisionError):
        return 0.0


def _cnn_ready(replay_buffer) -> bool:
    """
    Check if replay buffer has enough class diversity to activate CNN.
    Requires at least COLD_START_CLASSES_REQUIRED non-idle classes
    with >= COLD_START_CLASS_MIN samples each.
    """
    counts = replay_buffer.class_counts()
    non_idle_ready = sum(
        1 for cls, count in counts.items()
        if cls != IDLE and count >= COLD_START_CLASS_MIN
    )
    return non_idle_ready >= COLD_START_CLASSES_REQUIRED


_HISTORY_FILE = Path(__file__).parent / "watt_history.json"
_HISTORY_SAVE_INTERVAL = 4  # save every 4 ticks (~60s)


def _check_ntp() -> None:
    """Log NTP sync status at startup."""
    try:
        result = subprocess.run(
            ["timedatectl", "show", "--property=NTPSynchronized", "--value"],
            capture_output=True, text=True, timeout=5,
        )
        synced = result.stdout.strip() == "yes"
        print(f"  NTP: {'synchronized' if synced else 'NOT synchronized — time may be inaccurate'}")
    except (OSError, subprocess.TimeoutExpired):
        print("  NTP: check unavailable")


def _save_watt_history(timestamped_history: deque) -> None:
    """Persist timestamped watt history to JSON."""
    try:
        data = list(timestamped_history)
        _HISTORY_FILE.write_text(json.dumps(data))
    except OSError:
        pass


def _load_watt_history() -> deque:
    """Load watt history from JSON, filter to last 2h, fill gaps with None."""
    max_age = 2 * 3600  # 2 hours in seconds
    tick_interval = 15
    max_samples = int(max_age / tick_interval)  # 480

    try:
        data = json.loads(_HISTORY_FILE.read_text())
    except (OSError, json.JSONDecodeError, ValueError):
        return deque(maxlen=max_samples)

    if not data:
        return deque(maxlen=max_samples)

    now = time.time()
    cutoff = now - max_age

    # Filter to last 2h
    recent = [(ts, w) for ts, w in data if ts >= cutoff]
    if not recent:
        return deque(maxlen=max_samples)

    # Reconstruct with gaps: for each 15s slot from the oldest sample to now,
    # place the value if we have it, None if not
    result = deque(maxlen=max_samples)
    slot_start = recent[0][0]
    data_idx = 0

    t = slot_start
    while t <= now:
        if data_idx < len(recent) and abs(recent[data_idx][0] - t) < tick_interval * 0.8:
            result.append(recent[data_idx][1])
            data_idx += 1
        else:
            result.append(None)
        t += tick_interval

    return result


def _build_status_line(
    tick: int,
    watts: float,
    state: int,
    source: str,
    confidence: float,
    rolling_acc: float,
    buffer_size: int,
    drift: bool,
    training_loss: float | None,
) -> str:
    state_str = STATE_NAMES.get(state, "UNKNOWN")
    conf_pct = confidence * 100.0
    acc_pct = rolling_acc * 100.0
    loss_str = f"{training_loss:.4f}" if training_loss is not None else "—"
    drift_flag = " [DRIFT!]" if drift else ""
    return (
        f"[{tick:>5}] {watts:>7.1f} W  →  {state_str:<6}  "
        f"conf={conf_pct:4.1f}%  roll_acc={acc_pct:4.1f}%  "
        f"buf={buffer_size:>4}  loss={loss_str}  src={source}{drift_flag}"
    )


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    print("=== powermeter-active-learner starting ===")
    _check_ntp()

    # --- Verify PyTorch is available ---
    if not _TORCH_AVAILABLE:
        print(
            f"WARNING: PyTorch not available — running in baseline-only mode.\n"
            f"  {_TORCH_IMPORT_ERROR}"
        )

    # --- Instantiate components ---
    # --- Data source ---
    if USE_HA_SOURCE:
        ha_url = os.environ["HA_URL"]
        ha_token = os.environ["HA_TOKEN"]
        ha_entity = os.environ["HA_ENTITY_ID"]
        data_source = HomeAssistantDataSource(ha_url, ha_token, ha_entity)
        print(f"  Data source: Home Assistant ({ha_entity})")
    else:
        data_source = MockDataSource(washer=True, dryer=False)
        print("  Data source: MockDataSource (simulation)")

    signal_window = SignalWindow()
    multi_window = MultiScaleWindow()
    baseline = BaselineDetector()
    replay_buffer = ReplayBuffer()
    label_manager = LabelManager()
    confidence_tracker = ConfidenceTracker()
    drift_detector = DriftDetector()
    # Timestamped history for persistence: list of [epoch, watts]
    _ts_history: deque = deque(maxlen=480)
    # Display history (may contain None for gaps)
    watt_history: deque = _load_watt_history()
    print(f"  Watt history: loaded {sum(1 for v in watt_history if v is not None)}/{len(watt_history)} samples from disk")

    model: PowerNet | None = None
    trainer: Trainer | None = None

    if _TORCH_AVAILABLE:
        model = PowerNet(class_weights=CLASS_WEIGHTS)
        trainer = Trainer(model, class_weights=CLASS_WEIGHTS)
        loaded = trainer.load_checkpoint()
        print(
            f"  Model: PowerNet ({model.param_count} params)  "
            f"checkpoint={'loaded' if loaded else 'not found (cold start)'}"
        )
    else:
        print("  Model: BaselineDetector (threshold-based fallback)")

    # --- HAT display + buttons ---
    display = None
    buttons = None
    _display_lock = threading.Lock()
    _ui_state = UIState()
    _debug_state = DebugState() if _HAT_AVAILABLE else None
    _debug_view = [False]  # True = showing debug screen
    _standby_active = [False]
    _gate_ticks = [0]
    _STANDBY_THRESHOLD = 20  # 20 ticks * 15s = 5 minutes
    _proactive_washer = [False]  # mutable container for closure
    _proactive_dryer = [False]
    _start_time = time.time()

    if _HAT_AVAILABLE:
        display = EinkDisplay()
        display.init()
        display.clear()

        def _on_washer_toggle():
            _standby_active[0] = False
            _gate_ticks[0] = 0
            _proactive_washer[0] = not _proactive_washer[0]
            _proactive_dryer_val = _proactive_dryer[0]
            if _proactive_washer[0] and _proactive_dryer_val:
                gt = BOTH
            elif _proactive_washer[0]:
                gt = WASHER
            elif _proactive_dryer_val:
                gt = DRYER
            else:
                gt = IDLE
            raw = signal_window.get_raw() if signal_window.is_full() else []
            if raw:
                label_manager.add_proactive(gt, raw)
            with _display_lock:
                _ui_state.washer_on = _proactive_washer[0]
                frame = render_frame(_ui_state)
                display.show_image(frame)

        def _on_dryer_toggle():
            _standby_active[0] = False
            _gate_ticks[0] = 0
            _proactive_dryer[0] = not _proactive_dryer[0]
            _proactive_washer_val = _proactive_washer[0]
            if _proactive_washer_val and _proactive_dryer[0]:
                gt = BOTH
            elif _proactive_washer_val:
                gt = WASHER
            elif _proactive_dryer[0]:
                gt = DRYER
            else:
                gt = IDLE
            raw = signal_window.get_raw() if signal_window.is_full() else []
            if raw:
                label_manager.add_proactive(gt, raw)
            with _display_lock:
                _ui_state.dryer_on = _proactive_dryer[0]
                frame = render_frame(_ui_state)
                display.show_image(frame)

        _feedback_clear_time = [0.0]  # epoch time at which to clear feedback

        def _show_feedback(msg: str, duration_s: float = 30.0):
            _ui_state.feedback_msg = msg
            _feedback_clear_time[0] = time.time() + duration_s

        def _on_ok():
            _standby_active[0] = False
            _gate_ticks[0] = 0
            accepted = label_manager.confirm(ok=True)
            with _display_lock:
                if accepted:
                    _ui_state.has_pending = False
                    _show_feedback("YES sent!", 30)
                else:
                    _show_feedback("No pending pred", 5)
                frame = render_frame(_ui_state)
                display.show_image(frame)

        # Multi-click KEY4 detection:
        #   1 click = NO feedback
        #   2 clicks = toggle debug view
        #   3 clicks = safe poweroff
        _ko_click_times: list[float] = []
        _MULTI_CLICK_WINDOW = 0.8  # seconds to wait for additional clicks
        _ko_timer: list = [None]  # pending timer

        def _ko_execute():
            """Called after click window expires — decide action by click count."""
            count = len(_ko_click_times)
            _ko_click_times.clear()
            _ko_timer[0] = None

            if count >= 3:
                _safe_poweroff()
            elif count == 2:
                _toggle_debug_view()
            else:
                # Single click: normal NO feedback
                accepted = label_manager.confirm(ok=False)
                with _display_lock:
                    if accepted:
                        _ui_state.has_pending = False
                        _show_feedback("NO sent!", 30)
                    else:
                        _show_feedback("No pending pred", 5)
                    if _debug_view[0]:
                        frame = render_debug_frame(_debug_state)
                    else:
                        frame = render_frame(_ui_state)
                    display.show_image(frame)

        def _on_ko():
            _standby_active[0] = False
            _gate_ticks[0] = 0
            now = time.time()
            # Clear stale clicks
            while _ko_click_times and now - _ko_click_times[0] > _MULTI_CLICK_WINDOW:
                _ko_click_times.pop(0)
            _ko_click_times.append(now)

            # Cancel any pending timer and restart the window
            if _ko_timer[0] is not None:
                _ko_timer[0].cancel()
            _ko_timer[0] = threading.Timer(_MULTI_CLICK_WINDOW, _ko_execute)
            _ko_timer[0].daemon = True
            _ko_timer[0].start()

        def _safe_poweroff():
            """Signal the main loop to stop, then poweroff from the main thread."""
            print("[POWEROFF] Triple-click detected — signaling shutdown...")
            # Show immediate feedback on e-ink
            with _display_lock:
                from PIL import Image, ImageDraw, ImageFont
                from hat.epd import LANDSCAPE_W, LANDSCAPE_H
                img = Image.new("1", (LANDSCAPE_W, LANDSCAPE_H), 255)
                draw = ImageDraw.Draw(img)
                try:
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
                    font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
                except OSError:
                    font = ImageFont.load_default()
                    font_sm = font
                draw.text((50, 50), "Shutting down...", font=font, fill=0)
                draw.text((50, 80), "Wait for green LED off", font=font_sm, fill=0)
                draw.text((50, 100), "then unplug safely", font=font_sm, fill=0)
                display.show_image(img)
            # Signal main loop to exit and perform poweroff
            _shutdown["poweroff"] = True
            _shutdown["requested"] = True

        def _toggle_debug_view():
            """Double-click KEY4: toggle between normal and debug screen."""
            _debug_view[0] = not _debug_view[0]
            print(f"[DEBUG] View {'ON' if _debug_view[0] else 'OFF'}")
            with _display_lock:
                if _debug_view[0]:
                    frame = render_debug_frame(_debug_state)
                else:
                    frame = render_frame(_ui_state)
                display.show_image(frame)

        buttons = ButtonHandler({
            1: _on_washer_toggle,
            2: _on_dryer_toggle,
            3: _on_ok,
            4: _on_ko,
        })
        # Initial display
        _ui_state.timestamp = datetime.now().strftime("%H:%M:%S")
        with _display_lock:
            frame = render_frame(_ui_state)
            display.show_image(frame)
        print("  HAT: display + buttons initialized")

    # --- Graceful shutdown ---
    _shutdown = {"requested": False, "poweroff": False}

    def _handle_sigint(sig: int, frame: object) -> None:
        print("\nShutdown requested — saving checkpoint …")
        _shutdown["requested"] = True

    signal.signal(signal.SIGINT, _handle_sigint)
    signal.signal(signal.SIGTERM, _handle_sigint)

    # --- Main loop ---
    tick = 0
    print(
        f"  Tick interval: {TICK_INTERVAL} s  |  cold-start: "
        f"{COLD_START_CLASSES_REQUIRED} non-idle classes with >={COLD_START_CLASS_MIN} samples each"
        f"  |  idle gate: <{IDLE_GATE_W} W"
    )
    print("-" * 80)

    while not _shutdown["requested"]:
        tick += 1

        # 1. Read power (with error handling for HA)
        has_error = False
        try:
            watts = data_source.read_watts()
        except RuntimeError:
            watts = 0.0
            has_error = True

        # Defaults for status line
        state = IDLE
        confidence = 0.0
        inference_source = "none"
        training_loss: float | None = None
        blended_conf = 0.0
        _using_cnn = False
        idle_gated = False
        drift_detected = False

        # On API error: skip the entire pipeline for this tick
        # (don't inject fake 0W into the signal window or chart)
        if has_error:
            pass  # jump straight to display update with error icon
        else:
            # 2. Update window
            signal_window.add(watts)
            multi_window.add(watts)
            watt_history.append(watts)
            _ts_history.append([time.time(), watts])

            # Save history to disk periodically
            if tick % _HISTORY_SAVE_INTERVAL == 0:
                _save_watt_history(_ts_history)

            # 3. Drift detection (always on raw signal)
            drift_detected = drift_detector.update(watts)

            if multi_window.is_ready():
                raw_window = multi_window.get_raw()  # 5min raw for baseline + idle gate
                norm_window = signal_window.get_normalised()  # for replay buffer storage

                # 4. Classification

                # Idle gate: if the entire window is below IDLE_GATE_W,
                # skip CNN and use BaselineDetector (saves feedback budget,
                # avoids inflating confidence with trivial IDLE predictions)
                window_max = max(raw_window) if raw_window else 0.0
                idle_gated = window_max < IDLE_GATE_W

                use_cnn = (
                    _TORCH_AVAILABLE
                    and model is not None
                    and _cnn_ready(replay_buffer)
                )

                if idle_gated:
                    state = IDLE
                    confidence = 1.0
                    inference_source = "gate"
                    _using_cnn = False
                elif use_cnn and model is not None:
                    multi_channels = multi_window.get_multi_scale()
                    state, confidence = model.predict_with_confidence(multi_channels)
                    inference_source = "CNN"
                    _using_cnn = True
                else:
                    state = baseline.update(raw_window)
                    confidence = 0.0
                    inference_source = "baseline"

                # 4b. Compute blended confidence
                if idle_gated:
                    blended_conf = 1.0
                elif use_cnn:
                    blended_conf = confidence_blend(confidence, confidence_tracker)
                elif inference_source == "baseline":
                    blended_conf = baseline.pseudo_confidence(raw_window)
                else:
                    blended_conf = 0.0

                # 5. Notify label manager ONLY if not idle-gated and no pending feedback
                if not idle_gated and not label_manager.has_pending:
                    label_manager.notify_prediction(state, norm_window)

                # 6. Consume ready labels and push to replay buffer
                for event in label_manager.get_ready_labels():
                    source_str = (
                        "proactive"
                        if event.label_type.name == "PROACTIVE"
                        else "reactive"
                    )
                    replay_buffer.add(event.window, event.target_class, source_str)

                # 7. Maybe train
                if trainer is not None:
                    training_loss = trainer.maybe_train(
                        replay_buffer, min_samples=DEFAULT_BATCH_SIZE
                    )

        # 8. Print status (every 10 ticks or on state changes to reduce SD writes)
        if tick % 10 == 1 or state != IDLE or drift_detected or has_error:
            rolling_acc = confidence_tracker.get_rolling_accuracy()
            line = _build_status_line(
                tick=tick,
                watts=watts,
                state=state,
                source=inference_source,
                confidence=confidence,
                rolling_acc=rolling_acc,
                buffer_size=replay_buffer.size(),
                drift=drift_detected,
                training_loss=training_loss,
            )
            print(line)
            sys.stdout.flush()

        # 8b. Update HAT display (skip if poweroff in progress)
        if _HAT_AVAILABLE and display is not None and not _shutdown["poweroff"]:
            # Auto-clear feedback message based on real time
            if _ui_state.feedback_msg and time.time() >= _feedback_clear_time[0]:
                _ui_state.feedback_msg = ""

            # Track gate mode duration for standby
            if idle_gated and not has_error:
                _gate_ticks[0] += 1
            else:
                _gate_ticks[0] = 0
                _standby_active[0] = False

            # Check standby exit conditions
            pending = label_manager.pending_event
            if _standby_active[0]:
                if not idle_gated or has_error or pending is not None:
                    _standby_active[0] = False
                    _gate_ticks[0] = 0

            # Enter standby after 5 min of continuous gate
            if not _standby_active[0] and _gate_ticks[0] >= _STANDBY_THRESHOLD:
                _standby_active[0] = True
                with _display_lock:
                    frame = render_standby_frame()
                    display.show_image(frame)
                # Don't render anything else this tick
            elif _standby_active[0]:
                pass  # Display frozen, skip rendering entirely
            else:
                # Normal rendering
                with _display_lock:
                    _ui_state.watts = watts
                    _ui_state.state = state
                    _ui_state.confidence = blended_conf if multi_window.is_ready() else 0.0
                    _ui_state.timestamp = datetime.now().strftime("%H:%M:%S")
                    _ui_state.has_error = has_error
                    _ui_state.cpu_percent = _read_cpu_percent()
                    _ui_state.temperature = _read_temperature()
                    _ui_state.ram_percent = _read_ram_free()
                    _ui_state.model_loaded = "PowerNet" if _TORCH_AVAILABLE else "Baseline"
                    if idle_gated:
                        _ui_state.model_active = "Gate"
                    elif _using_cnn:
                        _ui_state.model_active = "PowerNet"
                    else:
                        _ui_state.model_active = "Baseline"
                    _ui_state.watt_history = list(watt_history)
                    # Reactive feedback state (single access to avoid TOCTOU race)
                    pending_ev = label_manager.pending_event
                    if pending_ev is not None:
                        _ui_state.has_pending = True
                        _ui_state.pending_state = pending_ev.target_class
                        _ui_state.pending_remaining_s = max(0, pending_ev.expires_at - time.time())
                    else:
                        _ui_state.has_pending = False

                    # Populate debug state
                    _debug_state.class_counts = replay_buffer.class_counts()
                    _debug_state.buffer_size = replay_buffer.size()
                    _debug_state.cold_start_ready = _cnn_ready(replay_buffer)
                    _debug_state.last_loss = training_loss
                    _debug_state.rolling_accuracy = confidence_tracker.get_rolling_accuracy()
                    _debug_state.evaluated_count = confidence_tracker.evaluated_count
                    _debug_state.drift_detected = drift_detected
                    _debug_state.model_loaded = _ui_state.model_loaded
                    _debug_state.model_active = _ui_state.model_active
                    _debug_state.timestamp = _ui_state.timestamp
                    _debug_state.uptime_s = time.time() - _start_time

                    # Render the active view
                    if _debug_view[0]:
                        frame = render_debug_frame(_debug_state)
                    else:
                        frame = render_frame(_ui_state)
                    display.show_image(frame)

        # 9. Sleep
        time.sleep(TICK_INTERVAL)

    # --- Clean shutdown ---
    _save_watt_history(_ts_history)  # persist watt history
    if trainer is not None:
        trainer.save_checkpoint()
        print("Checkpoint saved.")
    replay_buffer.close()

    if _shutdown["poweroff"] and _HAT_AVAILABLE and display is not None:
        # Show final "safe to unplug" message before powering off
        from PIL import Image, ImageDraw, ImageFont
        from hat.epd import LANDSCAPE_W, LANDSCAPE_H
        with _display_lock:
            img = Image.new("1", (LANDSCAPE_W, LANDSCAPE_H), 255)
            draw = ImageDraw.Draw(img)
            try:
                font_lg = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
                font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
            except OSError:
                font_lg = ImageFont.load_default()
                font_sm = font_lg
            # Centered shutdown-complete screen
            draw.text((62, 55), "POWER OFF", font=font_lg, fill=0)
            draw.text((42, 90), "Unplug when green LED", font=font_sm, fill=0)
            draw.text((72, 108), "stops flashing", font=font_sm, fill=0)
            display.show_image(img)
        print("[POWEROFF] Executing poweroff...")
        if buttons is not None:
            buttons.stop()
        display.sleep()
        subprocess.run(["sudo", "poweroff"], check=False)
    else:
        if buttons is not None:
            buttons.stop()
        if display is not None:
            display.sleep()
        print("Bye.")


if __name__ == "__main__":
    main()
