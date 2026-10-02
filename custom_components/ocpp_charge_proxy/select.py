"""Select platform for OCPP Charge Proxy."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, VALID_CURRENT_OPTIONS, get_device_info
from .coordinator import OCPPChargeProxyCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up select entities."""
    coordinator: OCPPChargeProxyCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([OCPPChargeProxyCurrentSelect(coordinator, entry)])


class OCPPChargeProxyCurrentSelect(CoordinatorEntity[OCPPChargeProxyCoordinator], SelectEntity):
    """Select entity for charger current setting."""

    _attr_has_entity_name = True
    _attr_name = "Current Amps Setting"
    _attr_options = VALID_CURRENT_OPTIONS

    def __init__(self, coordinator: OCPPChargeProxyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_current_amps_setting"
        self._attr_device_info = get_device_info(entry.entry_id)

    @property
    def current_option(self) -> str | None:
        """Return the current amps setting."""
        val = self.coordinator.data.get("current_amps_setting")
        return str(val) if val is not None else None

    @property
    def extra_state_attributes(self) -> dict:
        """The setting is the max; the provider can lower the current below it."""
        data = self.coordinator.data
        return {
            "effective_amps": data.get("current_amps_effective"),
            "provider_limit_amps": data.get("current_amps_provider_limit"),
        }

    async def async_select_option(self, option: str) -> None:
        """Set the charger current."""
        await self.coordinator.send_command("/api/current", {"amps": int(option)})
        await self.coordinator.async_request_refresh()
