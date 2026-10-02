"""Shared helpers for the integration tests."""

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ocpp_charge_proxy.const import DOMAIN

URL = "http://addon.test:8099"

# What the add-on's /api/state returns for an idle charger
ADDON_STATE = {
    "state": "Available",
    "plugged_in": False,
    "power_kw": 0.0,
    "voltage": 230.0,
    "current_a": 0.0,
    "frequency_hz": 50.0,
    "power_offered_kw": 0.0,
    "energy_kwh": 6612.523,
    "current_amps_setting": 16,
    "current_amps_effective": 16,
    "current_amps_provider_limit": 32,
    "transaction_id": None,
    "connected_to_server": True,
    "meter_interval": 60,
    "power_source": "simulated",
    "power_entity_value": None,
    "server_config": {},
    "last_command_received": None,
    "last_command_sent": None,
    "last_heartbeat": None,
    "soc_percent": None,
    "held_messages": 0,
    "schedule_enabled": False,
    "schedule_next": None,
    "replug": {"enabled": True, "after_min": 10, "attempts": 3, "status": "idle", "attempts_used": 0,
               "waiting_since": None, "next_replug_at": None, "last_replug": None},
}


def mock_addon(aioclient_mock, state=None):
    """Fake the add-on's API. /api/events 404 = no push, so the integration polls."""
    aioclient_mock.get(f"{URL}/api/state", json=state or ADDON_STATE)
    aioclient_mock.get(f"{URL}/api/events", status=404)
    for endpoint in ("plug", "unplug", "soc", "power", "current"):
        aioclient_mock.post(f"{URL}/api/{endpoint}", json={"status": "ok"})
    for endpoint in ("schedule", "replug"):
        aioclient_mock.post(f"{URL}/api/automation/{endpoint}", json={"status": "ok"})


async def setup_integration(hass, aioclient_mock, options=None, state=None):
    mock_addon(aioclient_mock, state)
    entry = MockConfigEntry(domain=DOMAIN, data={"api_url": URL}, options=options or {})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def unload(hass, entry):
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


def posted(aioclient_mock, endpoint: str) -> int:
    """How many times the integration POSTed to /api/<endpoint>."""
    return sum(
        1 for call in aioclient_mock.mock_calls
        if str(call[0]).upper() == "POST" and str(call[1]).endswith(f"/api/{endpoint}")
    )
