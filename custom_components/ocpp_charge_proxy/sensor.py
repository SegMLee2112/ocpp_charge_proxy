"""Sensor platform for OCPP Charge Proxy."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, get_device_info
from .coordinator import OCPPChargeProxyCoordinator

SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="state",
        name="State",
    ),
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
    SensorEntityDescription(
        key="power_source",
        name="Power Source",
    ),
)

# OCPP traffic: state is the action name, details are attributes
COMMAND_SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="last_command_received",
        name="Last Command Received",
        icon="mdi:message-arrow-left",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="last_command_sent",
        name="Last Command Sent",
        icon="mdi:message-arrow-right",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities."""
    coordinator: OCPPChargeProxyCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            *(OCPPChargeProxySensor(coordinator, entry, desc) for desc in SENSOR_DESCRIPTIONS),
            *(OCPPChargeProxyCommandSensor(coordinator, entry, desc)
              for desc in COMMAND_SENSOR_DESCRIPTIONS),
        ]
    )


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


class OCPPChargeProxyCommandSensor(OCPPChargeProxySensor):
    """Last OCPP command received from / sent to the server."""

    def _record(self) -> dict | None:
        record = self.coordinator.data.get(self.entity_description.key)
        return record if isinstance(record, dict) else None

    @property
    def native_value(self):
        """The OCPP action, e.g. RemoteStartTransaction."""
        record = self._record()
        return record.get("action") if record else None

    @property
    def extra_state_attributes(self) -> dict | None:
        record = self._record()
        if not record:
            return None
        return {
            "timestamp": record.get("timestamp"),
            "status": record.get("status"),
            "payload": record.get("payload"),
            "response": record.get("response"),
        }
