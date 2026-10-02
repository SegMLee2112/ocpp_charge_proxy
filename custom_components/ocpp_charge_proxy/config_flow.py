"""Config flow for OCPP Charge Proxy."""

from __future__ import annotations

import logging
import os
from typing import Any

import aiohttp

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

try:
    from homeassistant.components.hassio import HassioServiceInfo
except ImportError:
    HassioServiceInfo = None  # Supervisor not available (HA Core standalone)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .autoplug import DEFAULT_AUTO_PLUG_SOC

from .const import DOMAIN

logger = logging.getLogger(__name__)

API_PORT = 8099

POWER_SELECTOR = EntitySelector(EntitySelectorConfig(domain="sensor", device_class="power"))
SOC_SELECTOR = EntitySelector(EntitySelectorConfig(domain="sensor", device_class="battery"))


def _entity_fields(power: str = "", soc: str = "") -> dict:
    """Optional power + SoC entity pickers.

    Pre-filled with suggested_value rather than default, so a picker can be
    cleared to unset it (with default=..., clearing just restores the old one).
    """
    return {
        vol.Optional("power_entity", description={"suggested_value": power or None}): POWER_SELECTOR,
        vol.Optional("soc_entity", description={"suggested_value": soc or None}): SOC_SELECTOR,
    }


def _entity_options(user_input: dict) -> dict:
    return {
        "power_entity": user_input.get("power_entity") or "",
        "soc_entity": user_input.get("soc_entity") or "",
    }
ADDON_SLUG = "ocpp_charge_proxy"
SUPERVISOR_ADDONS_URL = "http://supervisor/addons"


def _hostname_for_slug(slug: str) -> str:
    """Supervisor add-on slug -> its hostname on the HA network.

    Add-ons from a repository get a slug like "e504bcf9_ocpp_charge_proxy"
    (repo hash prefix); the hostname is the slug with "_" replaced by "-".
    """
    return slug.replace("_", "-")


def _is_our_addon(slug: str) -> bool:
    return slug == ADDON_SLUG or slug.endswith(f"_{ADDON_SLUG}")


async def _installed_addon_slugs(hass) -> list[str]:
    """Slugs of installed OCPP Charge Proxy add-ons, via the Supervisor."""
    slugs: list[str] = []

    # 1. HA's cached Supervisor add-on info (no extra request)
    try:
        from homeassistant.components.hassio import get_addons_info

        info = get_addons_info(hass) or {}
        slugs.extend(slug for slug in info if _is_our_addon(slug))
    except Exception:  # hassio not loaded / API changed
        logger.debug("get_addons_info unavailable", exc_info=True)

    # 2. Ask the Supervisor API directly (HA Core has SUPERVISOR_TOKEN)
    token = os.environ.get("SUPERVISOR_TOKEN")
    if token:
        try:
            session = async_get_clientsession(hass)
            async with session.get(
                SUPERVISOR_ADDONS_URL,
                headers={"Authorization": f"Bearer {token}"},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                resp.raise_for_status()
                body = await resp.json()
            for addon in body.get("data", {}).get("addons", []):
                slug = addon.get("slug", "")
                if _is_our_addon(slug) and slug not in slugs:
                    slugs.append(slug)
        except Exception:
            logger.debug("Supervisor add-on lookup failed", exc_info=True)

    return slugs


async def _candidate_urls(hass) -> list[str]:
    """Likely add-on API URLs, most specific first."""
    urls = [
        f"http://{_hostname_for_slug(slug)}:{API_PORT}"
        for slug in await _installed_addon_slugs(hass)
    ]
    for fallback in (
        f"http://local-ocpp-charge-proxy:{API_PORT}",  # installed as a local add-on
        f"http://ocpp-charge-proxy:{API_PORT}",
        f"http://localhost:{API_PORT}",  # standalone / host network
    ):
        if fallback not in urls:
            urls.append(fallback)
    return urls


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
                options=_entity_options(user_input),
            )

        return self.async_show_form(
            step_id="hassio_confirm",
            data_schema=vol.Schema(_entity_fields()),
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
                    options=_entity_options(user_input),
                )
            errors["base"] = "cannot_connect"

        # Pre-fill the URL: find the installed add-on's real hostname (which
        # includes a repository-specific prefix) instead of guessing.
        candidates = await _candidate_urls(self.hass)
        default_url = ""
        for url in candidates:
            if await _try_connect(self.hass, url):
                default_url = url
                logger.info("Found add-on API at %s", url)
                break

        if not default_url:
            # Not reachable yet (e.g. add-on stopped) — still offer the best guess
            default_url = candidates[0]

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("api_url", default=default_url): str,
                    **_entity_fields(),
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
            # A cleared picker is simply missing: store "" so it's unset
            return self.async_create_entry(title="", data={
                **_entity_options(user_input),
                "auto_plug": bool(user_input.get("auto_plug", False)),
                "auto_plug_entity": user_input.get("auto_plug_entity") or "",
                "auto_plug_soc": int(user_input.get("auto_plug_soc", DEFAULT_AUTO_PLUG_SOC)),
            })

        options = self._config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                **_entity_fields(
                    power=options.get("power_entity", ""),
                    soc=options.get("soc_entity", ""),
                ),
                vol.Optional("auto_plug", default=options.get("auto_plug", False)): BooleanSelector(),
                vol.Optional(
                    "auto_plug_entity",
                    description={"suggested_value": options.get("auto_plug_entity") or None},
                ): SOC_SELECTOR,
                vol.Optional(
                    "auto_plug_soc", default=options.get("auto_plug_soc", DEFAULT_AUTO_PLUG_SOC),
                ): NumberSelector(NumberSelectorConfig(
                    min=1, max=99, step=1, unit_of_measurement="%",
                    mode=NumberSelectorMode.SLIDER,
                )),
            }),
        )
