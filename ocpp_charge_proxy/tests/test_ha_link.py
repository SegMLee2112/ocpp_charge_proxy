import asyncio

import pytest

from src.ha_link import HaLink, power_kw, soc_value, validate_settings
from src.shared_state import SharedState


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class Fake:
    def __init__(self):
        self.state = SharedState()
        self.power = []
        self.soc = []
        self.plugs = 0

    def set_power(self, kw):
        self.power.append(kw)

    async def set_soc(self, soc):
        self.soc.append(soc)

    async def plug(self):
        self.plugs += 1
        self.state.plugged_in = True


def _link(tmp_path=None, **settings):
    fake = Fake()
    link = HaLink(str(tmp_path) if tmp_path else None, fake.state, fake.set_power, fake.set_soc, fake.plug, token="t")
    if settings:
        _run(link.update_settings(settings))
    fake.power.clear()
    fake.soc.clear()
    return link, fake


def _added(**states):
    return {"a": {k: {"s": v, "a": {}} for k, v in states.items()}}


def _changed(entity_id, state):
    return {"c": {entity_id: {"+": {"s": state}}}}


# --- values ------------------------------------------------------------------


def test_power_units():
    assert power_kw({"state": "1370", "attributes": {"unit_of_measurement": "W"}}) == 1.37
    assert power_kw({"state": "1.37", "attributes": {"unit_of_measurement": "kW"}}) == 1.37
    assert power_kw({"state": "1370", "attributes": {}}) == 1.37  # W assumed
    assert power_kw({"state": "unavailable", "attributes": {}}) is None
    assert soc_value({"state": "64"}) == 64 and soc_value({"state": "140"}) is None


def test_validate_settings():
    s = validate_settings({"power_entity": "sensor.p", "auto_plug_soc": "25"})
    assert s["power_entity"] == "sensor.p" and s["auto_plug_soc"] == 25 and s["soc_entity"] == ""
    for bad in ({"plug_entity": "sensor.x"}, {"soc_entity": "binary_sensor.x"},
                {"auto_plug_soc": 0}, {"auto_plug_soc": "x"}, {"power_entity": 5}):
        with pytest.raises(ValueError):
            validate_settings(bad)


# --- following entities -------------------------------------------------------


def test_power_and_soc_sent_on_change():
    link, fake = _link(power_entity="sensor.p", soc_entity="sensor.soc")
    _run(link.handle_entities_event({"a": {
        "sensor.p": {"s": "2000", "a": {"unit_of_measurement": "W"}},
        "sensor.soc": {"s": "64", "a": {}},
    }}))
    assert fake.power == [2.0] and fake.soc == [64.0]
    _run(link.handle_entities_event({"c": {"sensor.p": {"+": {"s": "1.5", "a": {"unit_of_measurement": "kW"}}}}}))
    assert fake.power[-1] == 1.5
    _run(link.handle_entities_event(_changed("sensor.soc", "unavailable")))
    assert fake.soc[-1] is None


def test_unset_sensors_cleared():
    link, fake = _link(power_entity="sensor.p", soc_entity="sensor.soc")
    _run(link.update_settings({"power_entity": "", "soc_entity": ""}))
    assert fake.power == [None] and fake.soc == [None]
    assert link.watched == []


def test_car_connected_plugs_in_on_off_to_on_only():
    link, fake = _link(plug_entity="binary_sensor.cable")
    _run(link.handle_entities_event(_added(**{"binary_sensor.cable": "on"})))
    assert fake.plugs == 0  # first reading only
    _run(link.handle_entities_event(_changed("binary_sensor.cable", "off")))
    _run(link.handle_entities_event(_changed("binary_sensor.cable", "on")))
    assert fake.plugs == 1
    fake.state.plugged_in = True
    _run(link.handle_entities_event(_changed("binary_sensor.cable", "off")))
    assert fake.plugs == 1  # never unplugs


def test_auto_plug_on_soc_drop_watching_reporting_sensor():
    link, fake = _link(soc_entity="sensor.soc", auto_plug=True, auto_plug_soc=30)
    assert link.watched == ["sensor.soc"]
    _run(link.handle_entities_event(_added(**{"sensor.soc": "50"})))
    _run(link.handle_entities_event(_changed("sensor.soc", "29")))
    assert fake.plugs == 1
    snap = link.snapshot()["monitored_soc"]
    assert snap["soc"] == 29 and snap["source"] == "reporting SoC sensor" and snap["auto_plug"] is True


def test_auto_plug_monitor_sensor_not_reported():
    link, fake = _link(auto_plug=True, auto_plug_entity="sensor.away_soc", auto_plug_soc=30)
    _run(link.handle_entities_event(_added(**{"sensor.away_soc": "40"})))
    _run(link.handle_entities_event(_changed("sensor.away_soc", "20")))
    assert fake.plugs == 1 and fake.soc == []
    assert link.snapshot()["monitored_soc"]["source"] == "monitor sensor"


def test_auto_plug_off_without_a_sensor():
    link, _ = _link(auto_plug=True)
    assert link.auto_plug.enabled is False and link.watched == []


def test_settings_saved_and_configured_flag(tmp_path):
    link, _ = _link(tmp_path)
    assert link.configured is False
    _run(link.update_settings({"soc_entity": "sensor.soc"}))
    again, _ = _link(tmp_path)
    assert again.configured is True and again.settings["soc_entity"] == "sensor.soc"


def test_no_supervisor_means_link_off():
    fake = Fake()
    link = HaLink(None, fake.state, fake.set_power, fake.set_soc, fake.plug, token="")
    _run(link.run())  # returns at once
    assert link.available is False and "Supervisor" in link.error
