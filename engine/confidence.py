# engine/confidence.py
from collections import deque

# Rolling accuracy window
ROLLING_N = 50

# Page-Hinkley default parameters
PH_THRESHOLD = 50.0   # detection threshold (λ)
PH_DELTA = 0.005      # allowable slack (δ)


class ConfidenceTracker:
    """
    Tracks rolling prediction accuracy over the last N evaluated samples.

    A sample is "evaluated" when the user provides reactive feedback (OK/KO)
    or when a proactive label is available for comparison.
    """

    def __init__(self, n: int = ROLLING_N) -> None:
        self._n = n
        self._window: deque[int] = deque(maxlen=n)  # 1 = correct, 0 = wrong

    def update(self, predicted: int, actual: int) -> None:
        """Record one evaluated prediction."""
        self._window.append(1 if predicted == actual else 0)

    def get_rolling_accuracy(self) -> float:
        """Return fraction of correct predictions in the last N evaluations."""
        if not self._window:
            return 0.0
        return sum(self._window) / len(self._window)

    @property
    def evaluated_count(self) -> int:
        return len(self._window)


class DriftDetector:
    """
    Page-Hinkley test for detecting structural changes in the raw power signal.

    The test monitors the cumulative deviation of incoming values from a
    running mean.  When the cumulative sum drops below (mean - threshold)
    the detector fires, indicating a downward shift; the symmetric version
    detects upward shifts.

    References
    ----------
    Page, E.S. (1954). Continuous inspection schemes. Biometrika.
    Hinkley, D.V. (1971). Inference about the change-point from cumulative
        sum tests. Biometrika.
    """

    def __init__(
        self,
        threshold: float = PH_THRESHOLD,
        delta: float = PH_DELTA,
    ) -> None:
        self._threshold = threshold
        self._delta = delta
        self._reset()

    def update(self, value: float) -> bool:
        """
        Feed a new raw wattage sample to the detector.

        Returns True if drift is detected (call reset() externally if needed).
        """
        self._n += 1
        # Update running mean incrementally
        self._mean += (value - self._mean) / self._n

        # Cumulative sums for both directions
        self._m_up += value - self._mean - self._delta
        self._m_down += self._mean - value - self._delta

        # Clip at zero (reset to zero on new minimum/maximum)
        self._m_up = max(0.0, self._m_up)
        self._m_down = max(0.0, self._m_down)

        if self._m_up > self._threshold or self._m_down > self._threshold:
            self._reset()
            return True
        return False

    def reset(self) -> None:
        self._reset()

    def _reset(self) -> None:
        self._n: int = 0
        self._mean: float = 0.0
        self._m_up: float = 0.0    # cumulative sum (upward drift)
        self._m_down: float = 0.0  # cumulative sum (downward drift)
