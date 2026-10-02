"""The OCPP Charge Proxy integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .autoplug import DEFAULT_AUTO_PLUG_SOC
from .const import DOMAIN
from .coordinator import OCPPChargeProxyCoordinator

PLATFORMS = ["sensor", "binary_sensor", "switch", "select"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up OCPP Charge Proxy from a config entry."""
    coordinator = OCPPChargeProxyCoordinator(
        hass,
        config_entry=entry,
        api_url=entry.data["api_url"],
        power_entity=entry.options.get("power_entity", ""),
        soc_entity=entry.options.get("soc_entity", ""),
        auto_plug=entry.options.get("auto_plug", False),
        auto_plug_soc=entry.options.get("auto_plug_soc", DEFAULT_AUTO_PLUG_SOC),
        auto_plug_entity=entry.options.get("auto_plug_entity", ""),
        plug_entity=entry.options.get("plug_entity", ""),
    )
    await coordinator.async_config_entry_first_refresh()
    coordinator.async_start()  # push updates + entity tracking

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    entry.async_on_unload(entry.add_update_listener(_async_update_options))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload integration when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
