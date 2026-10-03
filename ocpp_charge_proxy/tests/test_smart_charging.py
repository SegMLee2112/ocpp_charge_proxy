from src.smart_charging import find_dispatch_sensors, provider_name, smart_charging

NOW = 1_790_000_000.0  # 2026-09-21T14:13:20Z


def _iso(t):
    import datetime
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).isoformat()


def _octopus(state="off", planned=(), completed=(), started=()):
    def items(slots):
        return [{"start": _iso(a), "end": _iso(b), "charge_in_kwh": k, "source": "smart-charge"} for a, b, k in slots]
    return {
        "entity_id": "binary_sensor.octopus_energy_a1b2_intelligent_dispatching",
        "state": state,
        "attributes": {"planned_dispatches": items(planned), "completed_dispatches": items(completed),
                       "started_dispatches": items(started), "friendly_name": "Intelligent Dispatching"},
    }


def test_not_found():
    states = [{"entity_id": "sensor.x", "state": "1", "attributes": {}},
              {"entity_id": "binary_sensor.y", "state": "on", "attributes": {"planned_dispatches": "nope"}}]
    assert smart_charging(states, NOW) == {"found": False}


def test_octopus_plan_merged_and_split_into_now_and_next():
    h = 3600
    sensor = _octopus(
        state="on",
        planned=[(NOW - 600, NOW + 1200, -1.5), (NOW + 1200, NOW + 3000, -2.0),  # now, joined
                 (NOW + 3 * h, NOW + 3.5 * h, -1.0)],
        completed=[(NOW - 10 * h, NOW - 9 * h, -6.0)],
    )
    out = smart_charging([{"entity_id": "sensor.other", "attributes": {}}, sensor], NOW)
    assert out["found"] and out["provider"] == "Octopus Energy" and out["dispatching"] is True
    assert out["current"]["end"] == _iso(NOW + 3000).replace("+00:00", "Z")
    assert out["current"]["charge_kwh"] == -3.5
    assert len(out["planned"]) == 1 and out["planned_kwh"] == -1.0
    assert [p["charge_kwh"] for p in out["periods"]] == [-6.0, -3.5, -1.0]


def test_edf_and_unknown_suppliers():
    edf = dict(_octopus(), entity_id="binary_sensor.edf_energy_x_intelligent_dispatching")
    other = dict(_octopus(), entity_id="binary_sensor.my_renamed_dispatching")
    sensors = find_dispatch_sensors([other, edf])
    assert [s["entity_id"] for s in sensors] == [edf["entity_id"], other["entity_id"]]  # known first
    out = smart_charging([other, edf], NOW)
    assert out["provider"] == "EDF Energy" and out["others"] == [other["entity_id"]]
    assert out["planned"] == [] and out["planned_kwh"] is None and out["current"] is None
    assert provider_name(other["entity_id"]) == "Your supplier"


def test_bad_items_ignored():
    sensor = _octopus()
    sensor["attributes"]["planned_dispatches"] = [{"start": "x", "end": None}, "junk",
                                                  {"start": _iso(NOW + 60), "end": _iso(NOW + 30)}]
    assert smart_charging([sensor], NOW)["planned"] == []
