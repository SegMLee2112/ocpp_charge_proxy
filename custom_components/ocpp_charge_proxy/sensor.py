"""Sensor platform for OCPP Charge Proxy.

Power, Energy (for the Energy dashboard) and Current. Everything else is on
the add-on's web page.
"""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, get_device_info
from .coordinator import OCPPChargeProxyCoordinator

SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="power_kw",
        name="Power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="kW",
    ),
    SensorEntityDescription(
        key="energy_kwh",
        name="Energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement="kWh",
    ),
    SensorEntityDescription(
        key="current_a",
        name="Current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="A",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities."""
    coordinator: OCPPChargeProxyCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(OCPPChargeProxySensor(coordinator, entry, desc) for desc in SENSOR_DESCRIPTIONS)


class OCPPChargeProxySensor(CoordinatorEntity[OCPPChargeProxyCoordinator], SensorEntity):
    """Sensor entity for OCPP Charge Proxy."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: OCPPChargeProxyCoordinator,
        entry: ConfigEntry,
        description: SensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = get_device_info(entry.entry_id)

    @property
    def native_value(self):
        """Return the sensor value."""
        return self.coordinator.data.get(self.entity_description.key)
