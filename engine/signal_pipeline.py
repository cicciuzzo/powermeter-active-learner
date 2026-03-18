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

# Thresholds used for pseudo-confidence distance calculation
_DECISION_THRESHOLDS = [IDLE_THRESHOLD, WASHER_MAX, DRYER_MIN]
_CONFIDENCE_MARGIN = 100.0  # W — full confidence at this distance from threshold


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

    def pseudo_confidence(self, raw_window: list[float]) -> float:
        """
        Confidence proxy for threshold-based classification.
        Based on distance from nearest decision boundary.
        """
        if not raw_window:
            return 0.0
        mean_w = sum(raw_window[-10:]) / min(len(raw_window), 10)
        min_dist = min(abs(mean_w - t) for t in _DECISION_THRESHOLDS)
        return min(min_dist / _CONFIDENCE_MARGIN, 1.0)

    @property
    def state(self) -> int:
        return self._current_state


# ---------------------------------------------------------------------------
# Multi-scale window configuration
# ---------------------------------------------------------------------------

SCALES = [
    # (name, raw_samples, output_samples)
    ("5min", 20, 20),      # 20 samples at 15s = 5 min, no downsampling
    ("30min", 120, 20),    # 120 samples at 15s = 30 min, downsample 6x
    ("1h", 240, 20),       # 240 samples at 15s = 1h, downsample 12x
    ("2h", 480, 20),       # 480 samples at 15s = 2h, downsample 24x
]

MULTI_SCALE_OUTPUT_LEN = 20  # samples per channel
MULTI_SCALE_CHANNELS = 4


class MultiScaleWindow:
    """
    Maintains 4 sliding windows at different time scales.
    Produces a [4, 20] array suitable for the multi-scale CNN.

    Each scale collects raw samples in a deque, then downsamples
    to 20 output samples using block averaging (not subsampling)
    to avoid aliasing.
    """

    def __init__(self) -> None:
        self._buffers: list[deque[float]] = [
            deque(maxlen=raw) for _, raw, _ in SCALES
        ]
        # Running min/max for normalization (shared across scales)
        self._run_min: float = float("inf")
        self._run_max: float = float("-inf")

    def add(self, value: float) -> None:
        """Append a new raw sample to all buffers."""
        for buf in self._buffers:
            buf.append(value)
        # Update running min/max with slow decay
        self._run_min = min(self._run_min * MIN_MAX_DECAY, value)
        self._run_max = max(self._run_max * MIN_MAX_DECAY, value)

    def is_ready(self) -> bool:
        """True when the shortest buffer (5min) is full."""
        return len(self._buffers[0]) == self._buffers[0].maxlen

    def get_multi_scale(self) -> list[list[float]]:
        """
        Return 4 channels of 20 normalized samples each.

        Short buffers that aren't full yet are zero-padded on the left.
        Each channel is independently min-max normalized to [0, 1].
        Downsampling uses block averaging.
        """
        channels: list[list[float]] = []
        for i, (_, raw_len, out_len) in enumerate(SCALES):
            buf = list(self._buffers[i])

            # Pad with zeros if buffer not full
            if len(buf) < raw_len:
                buf = [0.0] * (raw_len - len(buf)) + buf

            # Downsample by block averaging
            if raw_len > out_len:
                block_size = raw_len // out_len
                downsampled: list[float] = []
                for j in range(out_len):
                    start = j * block_size
                    end = start + block_size
                    block = buf[start:end]
                    downsampled.append(sum(block) / len(block))
                buf = downsampled

            # Normalize to [0, 1] using running min/max
            span = self._run_max - self._run_min
            if span < 1e-6:
                normalized = [0.0] * out_len
            else:
                normalized = [(v - self._run_min) / span for v in buf]

            channels.append(normalized)

        return channels

    def get_raw(self) -> list[float]:
        """Return raw samples from the shortest (5min) buffer for BaselineDetector."""
        return list(self._buffers[0])
