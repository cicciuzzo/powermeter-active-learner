# engine/label_manager.py
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

# Default timeout for reactive feedback (seconds)
REACTIVE_TIMEOUT = 600.0  # 10 minutes


class LabelType(Enum):
    PROACTIVE = auto()
    REACTIVE_PENDING = auto()
    REACTIVE_CONFIRMED = auto()   # user pressed OK
    REACTIVE_REJECTED = auto()    # user pressed KO


@dataclass
class LabelEvent:
    """A single labeling event with associated context."""

    timestamp: float
    label_type: LabelType
    target_class: int
    window: list[float]
    expires_at: float = field(default=0.0)   # only relevant for REACTIVE_PENDING

    def is_expired(self) -> bool:
        return (
            self.label_type == LabelType.REACTIVE_PENDING
            and time.time() > self.expires_at
        )

    def is_ready(self) -> bool:
        """True if this event can be consumed for training."""
        return self.label_type in (
            LabelType.PROACTIVE,
            LabelType.REACTIVE_CONFIRMED,
            LabelType.REACTIVE_REJECTED,
        )


class LabelManager:
    """
    Manages the labeling lifecycle for both proactive and reactive modes.

    Proactive labels (user presses button at appliance start/stop) are
    immediately ready for training.

    Reactive labels start as PENDING after a model prediction; the user has
    up to `timeout` seconds to confirm (OK) or reject (KO).  Expired
    pending events are silently discarded.
    """

    def __init__(self, timeout: float = REACTIVE_TIMEOUT) -> None:
        self._timeout = timeout
        self._ready: list[LabelEvent] = []
        self._pending: Optional[LabelEvent] = None   # at most one outstanding

    # ------------------------------------------------------------------
    # Proactive path
    # ------------------------------------------------------------------

    def add_proactive(self, label: int, window: list[float]) -> None:
        """Record a direct ground-truth label from a physical button press."""
        event = LabelEvent(
            timestamp=time.time(),
            label_type=LabelType.PROACTIVE,
            target_class=label,
            window=window,
        )
        self._ready.append(event)

    # ------------------------------------------------------------------
    # Reactive path
    # ------------------------------------------------------------------

    def notify_prediction(
        self, pred_class: int, window: list[float], timestamp: Optional[float] = None
    ) -> None:
        """
        Register a model prediction as a REACTIVE_PENDING event.

        Any previously unanswered pending event is discarded first (expired
        or superseded).
        """
        now = timestamp if timestamp is not None else time.time()
        self._pending = LabelEvent(
            timestamp=now,
            label_type=LabelType.REACTIVE_PENDING,
            target_class=pred_class,
            window=window,
            expires_at=now + self._timeout,
        )

    def confirm(self, ok: bool) -> bool:
        """
        Confirm (ok=True) or reject (ok=False) the last pending prediction.

        Returns True if the confirmation was accepted, False if the pending
        event has already expired or there is no pending event.
        """
        if self._pending is None:
            return False
        if self._pending.is_expired():
            self._pending = None
            return False

        self._pending.label_type = (
            LabelType.REACTIVE_CONFIRMED if ok else LabelType.REACTIVE_REJECTED
        )
        self._ready.append(self._pending)
        self._pending = None
        return True

    # ------------------------------------------------------------------
    # Consumer
    # ------------------------------------------------------------------

    def get_ready_labels(self) -> list[LabelEvent]:
        """
        Return and clear all label events ready for training.

        Also prunes any stale pending event while we're at it.
        """
        if self._pending is not None and self._pending.is_expired():
            self._pending = None

        ready = list(self._ready)
        self._ready.clear()
        return ready

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    @property
    def has_pending(self) -> bool:
        return self._pending is not None and not self._pending.is_expired()

    @property
    def pending_event(self) -> Optional[LabelEvent]:
        return self._pending if self.has_pending else None
