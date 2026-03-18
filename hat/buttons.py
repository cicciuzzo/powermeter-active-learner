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

    def __init__(
        self,
        callbacks: dict[int, Callable[[], None]],
        hold_callbacks: dict[int, Callable[[], None]] | None = None,
        hold_time: float = 2.0,
    ) -> None:
        """
        Parameters
        ----------
        callbacks : dict[int, Callable]
            Mapping from key number (1-4) to zero-argument callable (on press).
        hold_callbacks : dict[int, Callable] or None
            Mapping from key number to callable triggered on long press.
        hold_time : float
            Seconds to hold before triggering the hold callback.
        """
        self._buttons: list[Button] = []
        hold_callbacks = hold_callbacks or {}
        for key_num, gpio_pin in KEY_PINS.items():
            kwargs: dict = {"pull_up": True}
            if key_num in hold_callbacks:
                kwargs["hold_time"] = hold_time
            btn = Button(gpio_pin, **kwargs)
            if key_num in callbacks:
                btn.when_pressed = callbacks[key_num]
            if key_num in hold_callbacks:
                btn.when_held = hold_callbacks[key_num]
            self._buttons.append(btn)

    def stop(self) -> None:
        """Release all GPIO resources. Must be called during cleanup."""
        for btn in self._buttons:
            btn.close()
        self._buttons.clear()
