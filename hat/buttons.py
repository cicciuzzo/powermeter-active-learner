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
