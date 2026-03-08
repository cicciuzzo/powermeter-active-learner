# engine/signal_pipeline.py
from collections import deque

from engine import IDLE, WASHER, DRYER, BOTH

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------

WINDOW_SIZE = 40          # samples (~10 minutes at 15 s/sample)
MIN_MAX_DECAY = 0.9999    # slow decay for running min/max

# BaselineDetector thresholds (Watts)
IDLE_THRESHOLD = 100.0    # below this → IDLE
WASHER_MAX = 1200.0       # washer-only ceiling (both would be higher)
DRYER_MIN = 1800.0        # dryer alone starts around here

# Hysteresis band (Watts) — must cross threshold ± HYSTERESIS to trigger transition
HYSTERESIS = 80.0

# Moving average window for BaselineDetector
MA_WINDOW = 10


class SignalWindow:
    """
    Accumulates raw wattage samples in a sliding window and exposes a
    min-max normalised view.

    The running min/max are adaptive: they update on every new sample so
    the normalisation stays meaningful across long operation periods.
    """

    def __init__(self, size: int = WINDOW_SIZE) -> None:
        self._size = size
        self._raw: deque[float] = deque(maxlen=size)
        self._run_min: float = float("inf")
        self._run_max: float = float("-inf")

    def add(self, value: float) -> None:
        self._raw.append(value)
        # Update running extremes with slow decay toward current value
        if self._run_min == float("inf"):
            self._run_min = value
            self._run_max = value
        else:
            self._run_min = min(self._run_min * MIN_MAX_DECAY + value * (1 - MIN_MAX_DECAY), value)
            self._run_max = max(self._run_max * MIN_MAX_DECAY + value * (1 - MIN_MAX_DECAY), value)

    def is_full(self) -> bool:
        return len(self._raw) == self._size

    def get_raw(self) -> list[float]:
        return list(self._raw)

    def get_normalised(self) -> list[float]:
        """Return min-max normalised window in [0, 1]."""
        span = self._run_max - self._run_min
        if span < 1.0:
            # Avoid division by near-zero when signal is flat
            return [0.5] * len(self._raw)
        return [(x - self._run_min) / span for x in self._raw]

    @property
    def size(self) -> int:
        return self._size

    @property
    def current_length(self) -> int:
        return len(self._raw)


class BaselineDetector:
    """
    Adaptive threshold detector for 4-class state classification.

    Uses a moving average over the last MA_WINDOW samples plus local variance
    inside the full window.  Hysteresis prevents rapid oscillation around
    threshold boundaries.
    """

    def __init__(self) -> None:
        self._ma_buf: deque[float] = deque(maxlen=MA_WINDOW)
        self._current_state: int = IDLE
        # Track smoothed mean for hysteresis logic
        self._last_mean: float = 0.0

    def update(self, raw_window: list[float]) -> int:
        """
        Feed the latest raw window and return the current state estimate.

        Parameters
        ----------
        raw_window : list[float]
            Raw wattage values (not normalised).

        Returns
        -------
        int
            One of IDLE, WASHER, DRYER, BOTH.
        """
        if not raw_window:
            return self._current_state

        latest = raw_window[-1]
        self._ma_buf.append(latest)
        mean_w = sum(self._ma_buf) / len(self._ma_buf)

        # Compute local variance as secondary feature (distinguishes washer
        # bursts from dryer's steadier draw at similar average power)
        if len(raw_window) >= 4:
            mu = sum(raw_window) / len(raw_window)
            variance = sum((x - mu) ** 2 for x in raw_window) / len(raw_window)
        else:
            variance = 0.0

        new_state = self._classify(mean_w, variance)

        # Apply hysteresis: only switch if mean moved clearly past the threshold
        if new_state != self._current_state:
            moved = abs(mean_w - self._last_mean)
            if moved >= HYSTERESIS:
                self._current_state = new_state

        self._last_mean = mean_w
        return self._current_state

    def _classify(self, mean_w: float, variance: float) -> int:
        """Pure classification logic without hysteresis."""
        if mean_w < IDLE_THRESHOLD:
            return IDLE
        if mean_w > WASHER_MAX + DRYER_MIN:
            # Combined load is very high
            return BOTH
        if mean_w > DRYER_MIN:
            # High and relatively steady → dryer; high and variable → both
            if variance > 50_000:
                return BOTH
            return DRYER
        # Between IDLE_THRESHOLD and DRYER_MIN
        # Washer range: variable mid-power signal
        return WASHER

    @property
    def state(self) -> int:
        return self._current_state
