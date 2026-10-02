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
    async_add_entities([
        OCPPChargeProxyPlugSwitch(coordinator, entry),
        OCPPChargeProxyScheduleSwitch(coordinator, entry),
        OCPPChargeProxyReplugSwitch(coordinator, entry),
    ])


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


class OCPPChargeProxyScheduleSwitch(CoordinatorEntity[OCPPChargeProxyCoordinator], SwitchEntity):
    """Turns the add-on's plug-in schedule (set up in its web page) on or off."""

    _attr_has_entity_name = True
    _attr_name = "Schedule"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: OCPPChargeProxyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_schedule"
        self._attr_device_info = get_device_info(entry.entry_id)

    @property
    def available(self) -> bool:
        # Older add-ons don't have a schedule
        return super().available and "schedule_enabled" in (self.coordinator.data or {})

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.get("schedule_enabled")

    @property
    def extra_state_attributes(self) -> dict:
        nxt = self.coordinator.data.get("schedule_next") or {}
        return {"next_action": nxt.get("action"), "next_time": nxt.get("time")}

    async def _set(self, enabled: bool) -> None:
        await self.coordinator.send_command("/api/automation/schedule", {"enabled": enabled})
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set(False)


class OCPPChargeProxyReplugSwitch(CoordinatorEntity[OCPPChargeProxyCoordinator], SwitchEntity):
    """Auto re-plug when the provider doesn't start a session."""

    _attr_has_entity_name = True
    _attr_name = "Auto Re-plug"
    _attr_icon = "mdi:power-plug-battery"

    def __init__(self, coordinator: OCPPChargeProxyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_auto_replug"
        self._attr_device_info = get_device_info(entry.entry_id)

    @property
    def _replug(self) -> dict:
        return (self.coordinator.data or {}).get("replug") or {}

    @property
    def available(self) -> bool:
        return super().available and bool(self._replug)

    @property
    def is_on(self) -> bool | None:
        return self._replug.get("enabled")

    @property
    def extra_state_attributes(self) -> dict:
        r = self._replug
        return {
            "status": r.get("status"),
            "after_minutes": r.get("after_min"),
            "tries": r.get("attempts"),
            "tries_used": r.get("attempts_used"),
            "next_replug_at": r.get("next_replug_at"),
            "last_replug": r.get("last_replug"),
        }

    async def _set(self, enabled: bool) -> None:
        await self.coordinator.send_command("/api/automation/replug", {"enabled": enabled})
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set(False)
