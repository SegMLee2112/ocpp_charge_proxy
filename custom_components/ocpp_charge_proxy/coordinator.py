"""Data update coordinator for OCPP Charge Proxy."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import SCAN_INTERVAL

logger = logging.getLogger(__name__)


class OCPPChargeProxyCoordinator(DataUpdateCoordinator):
    """Coordinator that polls the OCPP Charge Proxy add-on API."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        api_url: str,
        power_entity: str = "",
    ) -> None:
        super().__init__(
            hass,
            logger,
            name="OCPP Charge Proxy",
            config_entry=config_entry,
            update_interval=timedelta(seconds=SCAN_INTERVAL),
        )
        self._api_url = api_url
        self._power_entity = power_entity
        self._session = async_get_clientsession(hass)

    async def _async_update_data(self) -> dict:
        try:
            if self._power_entity:
                await self._push_power_reading()

            async with self._session.get(
                f"{self._api_url}/api/state",
                timeout=10,
            ) as resp:
                resp.raise_for_status()
                return await resp.json()
        except Exception as err:
            raise UpdateFailed(f"Error communicating with add-on: {err}") from err

    async def _push_power_reading(self) -> None:
        """Read power entity from HA and push to the add-on."""
        try:
            state = self.hass.states.get(self._power_entity)
            if state is None or state.state in ("unavailable", "unknown"):
                power_kw = None
            else:
                power_kw = float(state.state) / 1000.0  # W to kW
        except (ValueError, TypeError):
            power_kw = None

        try:
            await self._session.post(
                f"{self._api_url}/api/power",
                json={"power_kw": power_kw},
                timeout=3,
            )
        except Exception:
            logger.debug("Failed to push power reading to add-on", exc_info=True)

    async def send_command(self, endpoint: str, json: dict | None = None) -> None:
        """Send a command to the add-on API."""
        url = f"{self._api_url}{endpoint}"
        try:
            async with self._session.post(url, json=json, timeout=5) as resp:
                resp.raise_for_status()
        except Exception as err:
            raise HomeAssistantError(f"Failed to send command: {err}") from err
