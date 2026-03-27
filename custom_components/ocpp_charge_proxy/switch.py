"""Switch platform for OCPP Charge Proxy."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, get_device_info
from .coordinator import OCPPChargeProxyCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switch entities."""
    coordinator: OCPPChargeProxyCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([OCPPChargeProxyPlugSwitch(coordinator, entry)])


class OCPPChargeProxyPlugSwitch(CoordinatorEntity[OCPPChargeProxyCoordinator], SwitchEntity):
    """Switch to simulate car plugged in / unplugged."""

    _attr_has_entity_name = True
    _attr_name = "Plugged In"

    def __init__(self, coordinator: OCPPChargeProxyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_plugged_in"
        self._attr_device_info = get_device_info(entry.entry_id)

    @property
    def is_on(self) -> bool | None:
        """Return whether the car is plugged in."""
        return self.coordinator.data.get("plugged_in")

    async def async_turn_on(self, **kwargs) -> None:
        """Simulate plugging in the car."""
        await self.coordinator.send_command("/api/plug")
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        """Simulate unplugging the car."""
        await self.coordinator.send_command("/api/unplug")
        await self.coordinator.async_request_refresh()
