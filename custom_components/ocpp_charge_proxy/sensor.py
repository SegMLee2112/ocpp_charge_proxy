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
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, get_device_info
from .coordinator import OCPPChargeProxyCoordinator

SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="state",
        name="OCPP Charge Proxy State",
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
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)

SOC_SOURCE_DESCRIPTION = SensorEntityDescription(
    key="soc_source",
    name="SoC Source",
    icon="mdi:battery-sync",
    device_class=SensorDeviceClass.ENUM,
    options=["entity", "no reading", "not set"],
    entity_category=EntityCategory.DIAGNOSTIC,
)

MONITORED_SOC_DESCRIPTION = SensorEntityDescription(
    key="monitored_soc",
    name="Monitored SoC",
    device_class=SensorDeviceClass.BATTERY,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement="%",
    entity_category=EntityCategory.DIAGNOSTIC,
)

HEARTBEAT_DESCRIPTION = SensorEntityDescription(
    key="last_heartbeat",
    name="Last Heartbeat",
    icon="mdi:heart-pulse",
    device_class=SensorDeviceClass.TIMESTAMP,
    entity_category=EntityCategory.DIAGNOSTIC,
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
            *(
                (OCPPChargeProxyStateSensor if desc.key == "state" else OCPPChargeProxySensor)(
                    coordinator, entry, desc,
                )
                for desc in SENSOR_DESCRIPTIONS
            ),
            OCPPChargeProxySocSourceSensor(coordinator, entry, SOC_SOURCE_DESCRIPTION),
            OCPPChargeProxyHeartbeatSensor(coordinator, entry, HEARTBEAT_DESCRIPTION),
            OCPPChargeProxyMonitoredSocSensor(coordinator, entry, MONITORED_SOC_DESCRIPTION),
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
            "summary": record.get("summary"),
            "status": record.get("status"),
            "round_trip_ms": record.get("round_trip_ms"),
            "message_id": record.get("message_id"),
            "payload": record.get("payload"),
            "response": record.get("response"),
            "recent": record.get("recent"),
        }


class OCPPChargeProxySocSourceSensor(OCPPChargeProxySensor):
    """Where the SoC reported to the provider comes from, like Power Source.

    entity:      a SoC sensor is set and has a value, which is being reported
    no reading:  a SoC sensor is set but has no usable value, so none is sent
    not set:     no SoC sensor; SoC is never reported and car-full is off
    """

    @property
    def native_value(self) -> str:
        if not self.coordinator.soc_entity:
            return "not set"
        if self.coordinator.data.get("soc_percent") is None:
            return "no reading"
        return "entity"

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "entity_id": self.coordinator.soc_entity or None,
            "soc_percent": self.coordinator.data.get("soc_percent"),
        }


class OCPPChargeProxyHeartbeatSensor(OCPPChargeProxySensor):
    """When the provider last answered a Heartbeat (stops moving if the link dies)."""

    def _heartbeat(self) -> dict | None:
        hb = self.coordinator.data.get("last_heartbeat")
        return hb if isinstance(hb, dict) else None

    @property
    def native_value(self):
        hb = self._heartbeat()
        return dt_util.parse_datetime(hb["timestamp"]) if hb and hb.get("timestamp") else None

    @property
    def extra_state_attributes(self) -> dict | None:
        hb = self._heartbeat()
        if not hb:
            return None
        return {
            "round_trip_ms": hb.get("round_trip_ms"),
            "interval_s": hb.get("interval_s"),
            "server_time": hb.get("server_time"),
            "clock_offset_s": hb.get("clock_offset_s"),
        }


class OCPPChargeProxyStateSensor(OCPPChargeProxySensor):
    """The charger's OCPP status, named "OCPP Charge Proxy State" everywhere.

    With has_entity_name, HA shows just "State" on the device page; a full
    name of its own makes it "OCPP Charge Proxy State" there too. The entity
    ID (sensor.ocpp_charge_proxy_state) is kept by HA's entity registry.
    """

    _attr_has_entity_name = False
    _attr_name = "OCPP Charge Proxy State"


class OCPPChargeProxyMonitoredSocSensor(OCPPChargeProxySensor):
    """The SoC that auto plug-in watches (the monitor sensor, else the reported SoC sensor)."""

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        entity_id = self.coordinator.monitored_soc_entity
        if entity_id:
            # Follow the watched sensor directly, not only on add-on updates
            self.async_on_remove(async_track_state_change_event(
                self.hass, [entity_id], self._watched_changed,
            ))

    @callback
    def _watched_changed(self, _event: Event) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self):
        return self.coordinator.monitored_soc()

    @property
    def extra_state_attributes(self) -> dict:
        auto_plug = self.coordinator.auto_plug
        return {
            "entity_id": self.coordinator.monitored_soc_entity or None,
            "source": self.coordinator.monitored_soc_source,
            "auto_plug": auto_plug.enabled,
            "threshold": auto_plug.threshold,
            "armed": auto_plug.armed,
        }
