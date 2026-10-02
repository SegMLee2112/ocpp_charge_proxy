"""Data update coordinator for OCPP Charge Proxy."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import PUSH_FALLBACK_SCAN_INTERVAL, SCAN_INTERVAL

logger = logging.getLogger(__name__)

# Seconds to wait before reconnecting to the add-on's event stream: quick at
# first (an add-on restart takes a few seconds), then backing off to 60s.
RECONNECT_DELAYS = (1, 2, 2, 3, 3, 5, 5, 5, 10, 20, 30, 60)

# Integration options from before 1.2.0, now set on the add-on's Simulation tab
SENSOR_OPTION_KEYS = ("power_entity", "soc_entity", "plug_entity", "auto_plug", "auto_plug_entity", "auto_plug_soc")


class OCPPChargeProxyCoordinator(DataUpdateCoordinator):
    """Keeps the add-on's state in HA.

    Prefers push: the add-on streams its state over /api/events and every
    event updates the entities at once. If the stream isn't available (older
    add-on, add-on restarting) it polls /api/state every SCAN_INTERVAL
    seconds instead. Your power / SoC / car sensors are read by the add-on
    itself (its Simulation tab).
    """

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry, api_url: str) -> None:
        super().__init__(
            hass,
            logger,
            name="OCPP Charge Proxy",
            config_entry=config_entry,
            update_interval=timedelta(seconds=SCAN_INTERVAL),
        )
        self._api_url = api_url
        self._session = async_get_clientsession(hass)
        self.push_connected = False

    # --- Polling (fallback) ------------------------------------------------

    async def _async_update_data(self) -> dict:
        try:
            async with self._session.get(
                f"{self._api_url}/api/state",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                resp.raise_for_status()
                return await resp.json()
        except Exception as err:
            raise UpdateFailed(f"Error communicating with add-on: {err}") from err

    # --- One-off move of the old sensor options to the add-on -----------------

    async def async_migrate_sensor_options(self) -> bool:
        """Copy pre-1.2.0 sensor options to the add-on. True once they're there
        (or there was nothing to copy), so the options can be cleared."""
        options = {k: v for k, v in self.config_entry.options.items() if k in SENSOR_OPTION_KEYS}
        if not options:
            return True
        try:
            async with self._session.post(
                f"{self._api_url}/api/sensors?only_if_unconfigured=1", json=options,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 404:
                    logger.warning(
                        "Update the OCPP Charge Proxy add-on to 1.2.0 or later: your power / "
                        "SoC / car sensors are now set on its Simulation tab",
                    )
                    return False
                resp.raise_for_status()
        except Exception as err:
            logger.warning("Couldn't move sensor settings to the add-on yet: %s", err)
            return False
        logger.info("Sensor settings moved to the add-on's Simulation tab")
        return True

    @callback
    def async_start(self) -> None:
        """Start push updates. Call once, after the first refresh."""
        self.config_entry.async_create_background_task(
            self.hass, self._listen_for_events(), "ocpp_charge_proxy_events",
        )

    # --- Push from the add-on (Server-Sent Events) -----------------------

    def _set_push(self, connected: bool) -> None:
        if connected == self.push_connected:
            return
        self.push_connected = connected
        self.update_interval = timedelta(
            seconds=PUSH_FALLBACK_SCAN_INTERVAL if connected else SCAN_INTERVAL
        )
        logger.debug("Add-on push updates %s", "connected" if connected else "lost; polling")
        if not connected:
            # The next poll was scheduled on the long push-fallback interval;
            # poll now so it reschedules on the short one
            self.hass.async_create_task(self.async_request_refresh())

    async def _listen_for_events(self) -> None:
        attempt = 0
        while True:
            try:
                async with self._session.get(
                    f"{self._api_url}/api/events",
                    # The add-on sends at least every 10s; 45s of silence = dead
                    timeout=aiohttp.ClientTimeout(total=None, sock_connect=10, sock_read=45),
                ) as resp:
                    if resp.status == 404:
                        logger.info("Add-on doesn't support push updates; polling instead")
                        self._set_push(False)
                        await asyncio.sleep(600)  # check again after an add-on update
                        continue
                    resp.raise_for_status()
                    attempt = 0
                    async for raw in resp.content:
                        line = raw.decode("utf-8", "replace").strip()
                        if not line.startswith("data:"):
                            continue
                        try:
                            data = json.loads(line[5:])
                        except ValueError:
                            continue
                        self._set_push(True)
                        self.async_set_updated_data(data)
            except asyncio.CancelledError:
                raise
            except Exception as err:
                logger.debug("Add-on event stream ended: %s", err)
            self._set_push(False)
            await asyncio.sleep(RECONNECT_DELAYS[min(attempt, len(RECONNECT_DELAYS) - 1)])
            attempt += 1

    # --- Commands --------------------------------------------------------

    async def send_command(self, endpoint: str, json: dict | None = None) -> None:
        """Send a command to the add-on API."""
        url = f"{self._api_url}{endpoint}"
        try:
            async with self._session.post(url, json=json, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                resp.raise_for_status()
        except Exception as err:
            raise HomeAssistantError(f"Failed to send command: {err}") from err
