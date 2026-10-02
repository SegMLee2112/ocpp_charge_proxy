"""Data update coordinator for OCPP Charge Proxy."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .autoplug import DEFAULT_AUTO_PLUG_SOC, AutoPlug
from .const import PUSH_FALLBACK_SCAN_INTERVAL, SCAN_INTERVAL

logger = logging.getLogger(__name__)

_UNKNOWN_STATES = ("unavailable", "unknown", "none", "")


class OCPPChargeProxyCoordinator(DataUpdateCoordinator):
    """Keeps the add-on's state in HA.

    Prefers push: the add-on streams its state over /api/events and every
    event updates the entities at once. If the stream isn't available (older
    add-on, add-on restarting) it polls /api/state every SCAN_INTERVAL
    seconds instead. Power and SoC entity values are sent to the add-on as
    soon as they change, and again on every poll.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        api_url: str,
        power_entity: str = "",
        soc_entity: str = "",
        auto_plug: bool = False,
        auto_plug_soc: float = DEFAULT_AUTO_PLUG_SOC,
        auto_plug_entity: str = "",
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
        self._soc_entity = soc_entity
        # Auto plug-in watches its own SoC sensor if one is set (e.g. a car that
        # may be away from home), else the reported SoC sensor. The monitor
        # sensor is never sent to the add-on / provider.
        self._auto_plug_entity = auto_plug_entity or soc_entity
        self._auto_plug = AutoPlug(bool(auto_plug and self._auto_plug_entity), auto_plug_soc)
        self._session = async_get_clientsession(hass)
        self.push_connected = False

    @property
    def soc_entity(self) -> str:
        """Configured car battery (SoC) entity, or "" if not set."""
        return self._soc_entity

    # --- Polling (fallback) ------------------------------------------------

    async def _async_update_data(self) -> dict:
        try:
            await self._push_entity_values()
            async with self._session.get(
                f"{self._api_url}/api/state",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                resp.raise_for_status()
                return await resp.json()
        except Exception as err:
            raise UpdateFailed(f"Error communicating with add-on: {err}") from err

    # --- Power / SoC entities -> add-on ----------------------------------

    def _entity_number(self, entity_id: str, scale: float = 1.0) -> float | None:
        state = self.hass.states.get(entity_id)
        if state is None or str(state.state).lower() in _UNKNOWN_STATES:
            return None
        try:
            return float(state.state) * scale
        except (ValueError, TypeError):
            return None

    async def _post(self, endpoint: str, body: dict) -> None:
        try:
            async with self._session.post(
                f"{self._api_url}{endpoint}", json=body,
                timeout=aiohttp.ClientTimeout(total=3),
            ) as resp:
                if resp.status == 404:
                    logger.debug("Add-on has no %s (older version)", endpoint)
        except Exception:
            logger.debug("Failed to push %s to add-on", endpoint, exc_info=True)

    async def _push_power(self) -> None:
        if self._power_entity:
            # W -> kW; None tells the add-on to fall back to the simulation
            await self._post("/api/power", {"power_kw": self._entity_number(self._power_entity, 0.001)})

    async def _push_soc(self) -> None:
        if self._soc_entity:
            soc = self._entity_number(self._soc_entity)
            if soc is not None and not 0 <= soc <= 100:
                soc = None
            await self._post("/api/soc", {"soc": soc})

    async def _check_auto_plug(self) -> None:
        if not self._auto_plug.enabled:
            return
        soc = self._entity_number(self._auto_plug_entity)
        if soc is not None and not 0 <= soc <= 100:
            soc = None
        plugged_in = (self.data or {}).get("plugged_in")
        if not self._auto_plug.should_plug(soc, plugged_in):
            return
        logger.info(
            "Car SoC %.0f%% dropped below %.0f%%: switching Plugged In on",
            soc, self._auto_plug.threshold,
        )
        try:
            await self.send_command("/api/plug")
        except HomeAssistantError as err:
            logger.warning("Auto plug-in failed: %s", err)
            self._auto_plug.armed = True  # try again on the next reading
            return
        await self.async_request_refresh()

    async def _push_entity_values(self) -> None:
        await self._push_power()
        await self._push_soc()
        await self._check_auto_plug()

    @callback
    def async_start(self) -> None:
        """Start push updates both ways. Call once, after the first refresh."""
        entry = self.config_entry
        if not self._soc_entity:
            # No SoC entity: make sure the add-on isn't still using an old one
            entry.async_create_background_task(
                self.hass, self._post("/api/soc", {"soc": None}), "ocpp_charge_proxy_clear_soc",
            )
        # entity -> what to do when it changes (one sensor can do both SoC jobs)
        tracked: dict[str, list] = {}
        for entity, action in (
            (self._power_entity, self._push_power),
            (self._soc_entity, self._push_soc),
            (self._auto_plug_entity if self._auto_plug.enabled else "", self._check_auto_plug),
        ):
            if entity:
                tracked.setdefault(entity, []).append(action)
        if tracked:
            @callback
            def _changed(event: Event) -> None:
                for action in tracked.get(event.data["entity_id"], ()):
                    self.hass.async_create_task(action())

            entry.async_on_unload(
                async_track_state_change_event(self.hass, list(tracked), _changed)
            )
        entry.async_create_background_task(
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

    async def _listen_for_events(self) -> None:
        backoff = 5
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
                    backoff = 5
                    # The add-on may have just (re)started without our sensor
                    # values; send them now rather than at the next change/poll
                    self.hass.async_create_task(self._push_entity_values())
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
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

    # --- Commands --------------------------------------------------------

    async def send_command(self, endpoint: str, json: dict | None = None) -> None:
        """Send a command to the add-on API."""
        url = f"{self._api_url}{endpoint}"
        try:
            async with self._session.post(url, json=json, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                resp.raise_for_status()
        except Exception as err:
            raise HomeAssistantError(f"Failed to send command: {err}") from err
