"""Binary sensor platform for OCPP Charge Proxy."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
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
    """Set up binary sensor entities."""
    coordinator: OCPPChargeProxyCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([OCPPChargeProxyConnectedSensor(coordinator, entry)])


class OCPPChargeProxyConnectedSensor(
    CoordinatorEntity[OCPPChargeProxyCoordinator], BinarySensorEntity
):
    """Binary sensor for OCPP server connection status."""

    _attr_has_entity_name = True
    _attr_name = "Connected to Server"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: OCPPChargeProxyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_connected_to_server"
        self._attr_device_info = get_device_info(entry.entry_id)

    @property
    def is_on(self) -> bool | None:
        """Return whether the proxy is connected to the OCPP server."""
        return self.coordinator.data.get("connected_to_server")
