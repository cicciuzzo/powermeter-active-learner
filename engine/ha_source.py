#!/usr/bin/env python3
"""
engine/ha_source.py — DataSource that reads watts from Home Assistant REST API.

Data flow: powermeter → Matter → rpi-hassio (HA) → REST API → rpi-learner.

Configuration via constructor args (typically from environment variables):
  HA_URL       — e.g. "https://<rpi-hassio-ip>:8123"
  HA_TOKEN     — Long-Lived Access Token from HA profile
  HA_ENTITY_ID — e.g. "sensor.smart_plug_power"
"""
import json
import ssl
import urllib.request
import urllib.error
from typing import Optional

from engine.data_source import DataSource


class HomeAssistantDataSource(DataSource):

    def __init__(self, url: str, token: str, entity_id: str, timeout: float = 10.0) -> None:
        self._endpoint = f"{url.rstrip('/')}/api/states/{entity_id}"
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self._timeout = timeout
        self._last_error: Optional[str] = None
        # Allow self-signed certs (common in home HA setups)
        self._ssl_ctx = ssl.create_default_context()
        self._ssl_ctx.check_hostname = False
        self._ssl_ctx.verify_mode = ssl.CERT_NONE

    def read_watts(self) -> float:
        req = urllib.request.Request(self._endpoint, headers=self._headers)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout, context=self._ssl_ctx) as resp:
                data = json.loads(resp.read().decode())
            state_str = data.get("state", "")
            if state_str in ("unavailable", "unknown"):
                raise RuntimeError(f"HA entity state: {state_str}")
            watts = float(state_str)
            self._last_error = None
            return watts
        except (urllib.error.URLError, ValueError, KeyError, RuntimeError) as exc:
            self._last_error = str(exc)
            raise RuntimeError(f"HA API error: {exc}") from exc

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    @property
    def has_error(self) -> bool:
        return self._last_error is not None
