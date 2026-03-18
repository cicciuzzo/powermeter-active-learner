# engine/data_source.py
import math
import random
import time
from abc import ABC, abstractmethod


class DataSource(ABC):
    """Abstract interface for power reading sources."""

    @abstractmethod
    def read_watts(self) -> float:
        """Return the current aggregated power reading in Watts."""
        ...


# ---------------------------------------------------------------------------
# Appliance power profiles
# ---------------------------------------------------------------------------

# Washing machine: alternates between heating phase (high W), drum rotation
# (medium W with bursts), rinse (low W), and spin (medium-high W).
_WM_PHASES = [
    # (duration_seconds, base_watts, noise_std, burst_prob, burst_extra_w)
    (600, 2100.0, 80.0, 0.05, 300.0),   # heating
    (480, 350.0,  60.0, 0.20, 150.0),   # wash / drum rotation
    (360, 200.0,  40.0, 0.10, 80.0),    # rinse
    (300, 600.0,  90.0, 0.08, 200.0),   # spin
]
_WM_CYCLE_DURATION = sum(p[0] for p in _WM_PHASES)

# Tumble dryer: steady high draw with slow periodic dip when drum reverses.
_TD_BASE_WATTS = 2400.0
_TD_NOISE_STD = 60.0
_TD_DIP_PERIOD = 45.0  # seconds
_TD_DIP_DEPTH = 200.0  # watts lost during reversal


def _washer_watts(t: float) -> float:
    """Wattage contributed by the washing machine at time t (seconds)."""
    phase_t = t % _WM_CYCLE_DURATION
    elapsed = 0.0
    for duration, base, noise_std, burst_prob, burst_extra in _WM_PHASES:
        if phase_t < elapsed + duration:
            w = base + random.gauss(0.0, noise_std)
            if random.random() < burst_prob:
                w += burst_extra
            return max(0.0, w)
        elapsed += duration
    return 0.0


def _dryer_watts(t: float) -> float:
    """Wattage contributed by the tumble dryer at time t (seconds)."""
    # Slow sinusoidal dip to simulate drum reversal
    dip = _TD_DIP_DEPTH * 0.5 * (1.0 - math.cos(2.0 * math.pi * t / _TD_DIP_PERIOD))
    w = _TD_BASE_WATTS - dip + random.gauss(0.0, _TD_NOISE_STD)
    return max(0.0, w)


class MockDataSource(DataSource):
    """
    Simulates a realistic combined power signal from a washing machine and/or
    tumble dryer.

    Parameters
    ----------
    washer : bool
        Include washing machine in the simulated load.
    dryer : bool
        Include tumble dryer in the simulated load.
    noise_floor : float
        Idle baseline noise in Watts (e.g. standby appliances, router, ...).
    start_time : float | None
        Reference epoch for the simulation clock.  Defaults to now.
    """

    def __init__(
        self,
        washer: bool = True,
        dryer: bool = False,
        noise_floor: float = 40.0,
        start_time: float | None = None,
    ) -> None:
        self._washer = washer
        self._dryer = dryer
        self._noise_floor = noise_floor
        self._t0 = start_time if start_time is not None else time.time()

    def read_watts(self) -> float:
        t = time.time() - self._t0
        total = self._noise_floor + random.gauss(0.0, 5.0)
        if self._washer:
            total += _washer_watts(t)
        if self._dryer:
            total += _dryer_watts(t)
        return max(0.0, total)

    @property
    def active_state(self) -> int:
        """Ground-truth state label for validation purposes."""
        from engine import IDLE, WASHER, DRYER, BOTH
        if self._washer and self._dryer:
            return BOTH
        if self._washer:
            return WASHER
        if self._dryer:
            return DRYER
        return IDLE
