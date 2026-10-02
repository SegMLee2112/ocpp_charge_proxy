"""Setting up the integration against a fake add-on."""

from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ocpp_charge_proxy import MOVED_TO_ADDON
from custom_components.ocpp_charge_proxy.const import DOMAIN

from .common import URL, mock_addon, posted, setup_integration, unload


async def test_entities_created(hass, aioclient_mock):
    entry = await setup_integration(hass, aioclient_mock)
    assert hass.states.get("switch.ocpp_charge_proxy_plugged_in").state == "off"
    assert hass.states.get("sensor.ocpp_charge_proxy_energy").state == "6612.523"
    assert hass.states.get("sensor.ocpp_charge_proxy_power").state == "0.0"
    assert hass.states.get("sensor.ocpp_charge_proxy_current").state == "0.0"
    # Everything else is on the add-on's web page
    assert hass.states.get("sensor.ocpp_charge_proxy_state") is None
    assert hass.states.get("binary_sensor.ocpp_charge_proxy_connected_to_server") is None
    assert len(hass.states.async_entity_ids()) == 4
    await unload(hass, entry)


async def test_manual_plug_in_and_out(hass, aioclient_mock):
    entry = await setup_integration(hass, aioclient_mock)
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.ocpp_charge_proxy_plugged_in"}, blocking=True,
    )
    assert posted(aioclient_mock, "plug") == 1
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.ocpp_charge_proxy_plugged_in"}, blocking=True,
    )
    assert posted(aioclient_mock, "unplug") == 1
    await unload(hass, entry)


async def test_old_sensor_options_moved_to_addon(hass, aioclient_mock):
    old = {"power_entity": "", "soc_entity": "sensor.car_soc", "plug_entity": "binary_sensor.cable",
           "auto_plug": True, "auto_plug_entity": "", "auto_plug_soc": 25}
    entry = await setup_integration(hass, aioclient_mock, old)
    calls = [c for c in aioclient_mock.mock_calls if str(c[1]).split("?")[0].endswith("/api/sensors")]
    assert len(calls) == 1 and calls[0][2] == old
    assert "only_if_unconfigured" in str(calls[0][1])
    assert entry.options == {}  # copied, so cleared
    await unload(hass, entry)


async def test_old_options_kept_until_addon_takes_them(hass, aioclient_mock):
    mock_addon(aioclient_mock, sensors_status=404)  # add-on older than 1.2.0
    entry = MockConfigEntry(domain=DOMAIN, data={"api_url": URL}, options={"soc_entity": "sensor.car_soc"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.options == {"soc_entity": "sensor.car_soc"}
    await unload(hass, entry)


async def test_entities_moved_to_addon_removed(hass, aioclient_mock):
    mock_addon(aioclient_mock)
    entry = MockConfigEntry(domain=DOMAIN, data={"api_url": URL})
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    for platform, key in MOVED_TO_ADDON:
        registry.async_get_or_create(platform, DOMAIN, f"{entry.entry_id}_{key}", config_entry=entry)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    for platform, key in MOVED_TO_ADDON:
        assert registry.async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{key}") is None
    await unload(hass, entry)
