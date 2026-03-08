#!/usr/bin/env python3
"""
main.py — Entry point for the powermeter-active-learner system.

Runs a continuous loop (15-second ticks) that:
  1. Reads current power consumption (W) from a DataSource.
  2. Accumulates readings in a SignalWindow.
  3. Once the window is full, classifies the state via:
       - BaselineDetector during cold-start (replay buffer < COLD_START_MIN)
       - PowerNet (1D-CNN) after sufficient labeled data has been collected.
  4. Feeds the raw reading to the DriftDetector.
  5. Manages labeling events and triggers incremental training when possible.
  6. Prints a human-readable status line to stdout.

Graceful Ctrl-C saves the model checkpoint before exiting.
"""

import signal
import sys
import time

from engine import IDLE, WASHER, DRYER, BOTH, STATE_NAMES
from engine.data_source import MockDataSource
from engine.signal_pipeline import SignalWindow, BaselineDetector
from engine.replay_buffer import ReplayBuffer
from engine.label_manager import LabelManager
from engine.confidence import ConfidenceTracker, DriftDetector

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
COLD_START_MIN = 100        # samples in buffer before switching to CNN
DEFAULT_BATCH_SIZE = 32

# Class weights: IDLE is ~70 % of real-world time, so up-weight rare classes
CLASS_WEIGHTS = [0.3, 1.5, 1.5, 2.0]   # [IDLE, WASHER, DRYER, BOTH]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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

    # --- Verify PyTorch is available ---
    if not _TORCH_AVAILABLE:
        print(
            f"WARNING: PyTorch not available — running in baseline-only mode.\n"
            f"  {_TORCH_IMPORT_ERROR}"
        )

    # --- Instantiate components ---
    data_source = MockDataSource(washer=True, dryer=False)
    signal_window = SignalWindow()
    baseline = BaselineDetector()
    replay_buffer = ReplayBuffer()
    label_manager = LabelManager()
    confidence_tracker = ConfidenceTracker()
    drift_detector = DriftDetector()

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

    # --- Graceful shutdown ---
    _shutdown = {"requested": False}

    def _handle_sigint(sig: int, frame: object) -> None:
        print("\nShutdown requested — saving checkpoint …")
        _shutdown["requested"] = True

    signal.signal(signal.SIGINT, _handle_sigint)

    # --- Main loop ---
    tick = 0
    print(f"  Tick interval: {TICK_INTERVAL} s  |  cold-start threshold: {COLD_START_MIN} samples")
    print("-" * 80)

    while not _shutdown["requested"]:
        tick += 1

        # 1. Read power
        watts = data_source.read_watts()

        # 2. Update window
        signal_window.add(watts)

        # 3. Drift detection (always on raw signal)
        drift_detected = drift_detector.update(watts)

        # Defaults for status line before window is full
        state = IDLE
        confidence = 0.0
        inference_source = "none"
        training_loss: float | None = None

        if signal_window.is_full():
            raw_window = signal_window.get_raw()
            norm_window = signal_window.get_normalised()

            # 4. Classification
            use_cnn = (
                _TORCH_AVAILABLE
                and model is not None
                and replay_buffer.size() >= COLD_START_MIN
            )

            if use_cnn and model is not None:
                state, confidence = model.predict_with_confidence(norm_window)
                inference_source = "CNN"
            else:
                state = baseline.update(raw_window)
                confidence = 0.0   # baseline doesn't produce probabilities
                inference_source = "baseline"

            # 5. Notify label manager of prediction
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

        # 8. Print status
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

        # 9. Sleep
        time.sleep(TICK_INTERVAL)

    # --- Clean shutdown ---
    if trainer is not None:
        trainer.save_checkpoint()
        print("Checkpoint saved.")
    replay_buffer.close()
    print("Bye.")


if __name__ == "__main__":
    main()
