"""Config flow for OCPP Charge Proxy."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

try:
    from homeassistant.components.hassio import HassioServiceInfo
except ImportError:
    HassioServiceInfo = None  # Supervisor not available (HA Core standalone)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import EntitySelector, EntitySelectorConfig

from .const import DOMAIN

logger = logging.getLogger(__name__)

API_PORT = 8099


async def _try_connect(hass, url: str) -> bool:
    """Test if the API is reachable at this URL."""
    try:
        session = async_get_clientsession(hass)
        async with session.get(f"{url}/api/state", timeout=3) as resp:
            resp.raise_for_status()
            return True
    except Exception:
        return False


class OCPPChargeProxyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OCPP Charge Proxy."""

    VERSION = 1

    _discovered_url: str | None = None

    async def async_step_hassio(
        self, discovery_info: HassioServiceInfo,
    ) -> config_entries.ConfigFlowResult:
        """Handle Supervisor discovery."""
        config = discovery_info.config
        host = config.get("host", "")
        port = config.get("port", API_PORT)
        url = f"http://{host}:{port}"

        logger.info("Discovered add-on API at %s", url)

        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured(updates={"api_url": url})

        if await _try_connect(self.hass, url):
            self._discovered_url = url
            return await self.async_step_hassio_confirm()

        return self.async_abort(reason="cannot_connect")

    async def async_step_hassio_confirm(
        self, user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Confirm Supervisor discovery."""
        if user_input is not None:
            return self.async_create_entry(
                title="OCPP Charge Proxy",
                data={"api_url": self._discovered_url},
                options={"power_entity": user_input.get("power_entity", "")},
            )

        return self.async_show_form(
            step_id="hassio_confirm",
            data_schema=vol.Schema(
                {
                    vol.Optional("power_entity"): EntitySelector(
                        EntitySelectorConfig(domain="sensor", device_class="power")
                    ),
                }
            ),
            description_placeholders={"url": self._discovered_url},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle manual configuration."""
        errors = {}

        if user_input is not None:
            api_url = user_input["api_url"].rstrip("/")
            if await _try_connect(self.hass, api_url):
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="OCPP Charge Proxy",
                    data={"api_url": api_url},
                    options={"power_entity": user_input.get("power_entity", "")},
                )
            errors["base"] = "cannot_connect"

        # Try auto-discovery as fallback
        default_url = ""
        candidates = [
            f"http://ocpp-charge-proxy:{API_PORT}",
            f"http://localhost:{API_PORT}",
        ]
        for url in candidates:
            if await _try_connect(self.hass, url):
                default_url = url
                break

        if not default_url:
            default_url = f"http://localhost:{API_PORT}"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("api_url", default=default_url): str,
                    vol.Optional("power_entity"): EntitySelector(
                        EntitySelectorConfig(domain="sensor", device_class="power")
                    ),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OCPPChargeProxyOptionsFlow:
        """Get the options flow handler."""
        return OCPPChargeProxyOptionsFlow(config_entry)


# Use OptionsFlowWithConfigEntry if available (HA 2025.x+), fall back to OptionsFlow
_OptionsBase = getattr(config_entries, "OptionsFlowWithConfigEntry", config_entries.OptionsFlow)


class OCPPChargeProxyOptionsFlow(_OptionsBase):
    """Handle options for OCPP Charge Proxy."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry
        super().__init__(config_entry)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self._config_entry.options.get("power_entity", "")

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional("power_entity", default=current): EntitySelector(
                        EntitySelectorConfig(domain="sensor", device_class="power")
                    ),
                }
            ),
        )
