"""Setting up the integration against a fake add-on."""

from .common import ADDON_STATE, posted, setup_integration, unload


async def test_entities_created(hass, aioclient_mock):
    entry = await setup_integration(hass, aioclient_mock)
    assert hass.states.get("sensor.ocpp_charge_proxy_state").state == "Available"
    assert hass.states.get("sensor.ocpp_charge_proxy_state").name == "OCPP Charge Proxy State"
    assert hass.states.get("sensor.ocpp_charge_proxy_power_source").state == "simulated"
    assert hass.states.get("sensor.ocpp_charge_proxy_soc_source").state == "not set"
    assert hass.states.get("switch.ocpp_charge_proxy_plugged_in").state == "off"
    assert hass.states.get("select.ocpp_charge_proxy_current_amps_setting").state == "16"
    assert hass.states.get("binary_sensor.ocpp_charge_proxy_connected_to_server").state == "on"
    await unload(hass, entry)


async def test_manual_plug_in(hass, aioclient_mock):
    entry = await setup_integration(hass, aioclient_mock)
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.ocpp_charge_proxy_plugged_in"}, blocking=True,
    )
    assert posted(aioclient_mock, "plug") == 1
    await unload(hass, entry)


async def test_car_connected_sensor_plugs_in_when_it_turns_on(hass, aioclient_mock):
    hass.states.async_set("binary_sensor.car_cable", "off")
    entry = await setup_integration(hass, aioclient_mock, {"plug_entity": "binary_sensor.car_cable"})
    assert posted(aioclient_mock, "plug") == 0

    hass.states.async_set("binary_sensor.car_cable", "on")
    await hass.async_block_till_done()
    assert posted(aioclient_mock, "plug") == 1
    await unload(hass, entry)


async def test_car_connected_sensor_never_unplugs(hass, aioclient_mock):
    hass.states.async_set("binary_sensor.car_cable", "on")
    plugged = {**ADDON_STATE, "plugged_in": True, "state": "Preparing"}
    entry = await setup_integration(
        hass, aioclient_mock, {"plug_entity": "binary_sensor.car_cable"}, state=plugged,
    )
    hass.states.async_set("binary_sensor.car_cable", "off")
    await hass.async_block_till_done()
    assert posted(aioclient_mock, "unplug") == 0
    await unload(hass, entry)


async def test_car_connected_sensor_ignores_startup_and_unavailable(hass, aioclient_mock):
    """Connected at startup: no plug-in. on -> unavailable -> on: not a new connection."""
    hass.states.async_set("binary_sensor.car_cable", "on")
    entry = await setup_integration(hass, aioclient_mock, {"plug_entity": "binary_sensor.car_cable"})
    hass.states.async_set("binary_sensor.car_cable", "unavailable")
    await hass.async_block_till_done()
    hass.states.async_set("binary_sensor.car_cable", "on")
    await hass.async_block_till_done()
    assert posted(aioclient_mock, "plug") == 0
    await unload(hass, entry)


async def test_switch_usable_by_hand_with_car_connected_sensor(hass, aioclient_mock):
    hass.states.async_set("binary_sensor.car_cable", "off")
    entry = await setup_integration(hass, aioclient_mock, {"plug_entity": "binary_sensor.car_cable"})
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.ocpp_charge_proxy_plugged_in"}, blocking=True,
    )
    assert posted(aioclient_mock, "plug") == 1
    await unload(hass, entry)


async def test_auto_plug_in_on_soc_drop(hass, aioclient_mock):
    hass.states.async_set("sensor.car_soc", "50")
    entry = await setup_integration(hass, aioclient_mock, {
        "soc_entity": "sensor.car_soc", "auto_plug": True, "auto_plug_soc": 30,
    })
    hass.states.async_set("sensor.car_soc", "29")
    await hass.async_block_till_done()
    assert posted(aioclient_mock, "plug") == 1
    monitored = hass.states.get("sensor.ocpp_charge_proxy_monitored_soc")
    assert float(monitored.state) == 29
    await unload(hass, entry)


async def test_auto_plug_works_alongside_car_connected_sensor(hass, aioclient_mock):
    hass.states.async_set("sensor.car_soc", "50")
    hass.states.async_set("binary_sensor.car_cable", "off")
    entry = await setup_integration(hass, aioclient_mock, {
        "soc_entity": "sensor.car_soc", "plug_entity": "binary_sensor.car_cable",
        "auto_plug": True, "auto_plug_soc": 30,
    })
    hass.states.async_set("sensor.car_soc", "20")
    await hass.async_block_till_done()
    assert posted(aioclient_mock, "plug") == 1
    await unload(hass, entry)


async def test_soc_is_sent_to_addon(hass, aioclient_mock):
    hass.states.async_set("sensor.car_soc", "64")
    entry = await setup_integration(hass, aioclient_mock, {"soc_entity": "sensor.car_soc"})
    assert posted(aioclient_mock, "soc") >= 1
    hass.states.async_set("sensor.car_soc", "65")
    await hass.async_block_till_done()
    assert posted(aioclient_mock, "soc") >= 2
    await unload(hass, entry)
