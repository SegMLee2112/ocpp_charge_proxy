"""The OCPP Charge Proxy integration.

Gives Home Assistant the charger's Power, Energy and Current sensors and the
Plugged In switch. Everything else is set up and shown on the add-on's web
page.
"""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .coordinator import OCPPChargeProxyCoordinator

PLATFORMS = ["sensor", "switch"]

# Entities earlier versions created that now live only on the add-on's page
MOVED_TO_ADDON = (
    ("select", "current_amps_setting"),
    ("sensor", "last_command_received"),
    ("sensor", "last_command_sent"),
    ("sensor", "last_heartbeat"),
    ("sensor", "power_source"),
    ("sensor", "soc_source"),
    ("sensor", "monitored_soc"),
    ("sensor", "state"),
    ("binary_sensor", "connected_to_server"),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up OCPP Charge Proxy from a config entry."""
    coordinator = OCPPChargeProxyCoordinator(hass, config_entry=entry, api_url=entry.data["api_url"])
    await coordinator.async_config_entry_first_refresh()
    if entry.options and await coordinator.async_migrate_sensor_options():
        hass.config_entries.async_update_entry(entry, options={})
    coordinator.async_start()  # push updates

    _remove_old_entities(hass, entry)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


def _remove_old_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    registry = er.async_get(hass)
    for platform, key in MOVED_TO_ADDON:
        entity_id = registry.async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{key}")
        if entity_id:
            registry.async_remove(entity_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
