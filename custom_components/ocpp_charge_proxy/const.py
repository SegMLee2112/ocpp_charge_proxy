"""Constants for the OCPP Charge Proxy integration."""

from homeassistant.helpers.entity import DeviceInfo

DOMAIN = "ocpp_charge_proxy"
SCAN_INTERVAL = 10  # polling when the add-on can't push updates
PUSH_FALLBACK_SCAN_INTERVAL = 300  # safety poll while push updates are working


def get_device_info(entry_id: str) -> DeviceInfo:
    """Return shared DeviceInfo for all entities."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry_id)},
        name="OCPP Charge Proxy",
        manufacturer="OCPP Charge Proxy",
        model="Virtual Chargepoint",
    )
