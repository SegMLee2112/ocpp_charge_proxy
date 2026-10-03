import asyncio
import datetime

from src.automation import Automation, apply_ready_time
from src.ready_time import (
    ALL_DAY_TIMES, DEFAULT_TIMES, allowed_times, pick_ready_time, service_call, target_time_entity,
)

TZ = datetime.timezone(datetime.timedelta(hours=1))
DISPATCH = "binary_sensor.octopus_energy_abc_intelligent_dispatching"


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _at(day, h, m=0):
    return datetime.datetime(2026, 10, day, h, m, tzinfo=TZ)


def test_default_times_are_kraken_range():
    assert DEFAULT_TIMES[0] == "04:00" and DEFAULT_TIMES[-1] == "11:00" and len(DEFAULT_TIMES) == 15


def test_pick_latest_allowed_time_before_the_unplug():
    allowed = DEFAULT_TIMES
    # Schedule 2-4, 6-8, 10-12 (plugged in at 2, 6 and 10)
    assert pick_ready_time(_at(5, 2), _at(5, 4), allowed) == _at(5, 4)
    assert pick_ready_time(_at(5, 6), _at(5, 8), allowed) == _at(5, 8)
    assert pick_ready_time(_at(5, 10), _at(5, 12), allowed) == _at(5, 11)  # 11:00 is the latest accepted
    # Overnight: plugged in 23:30, unplugged 07:15 -> 07:00
    assert pick_ready_time(_at(5, 23, 30), _at(6, 7, 15), allowed) == _at(6, 7)
    # 4pm to 10pm: no accepted time in between
    assert pick_ready_time(_at(5, 16), _at(5, 22), allowed) is None


def test_target_time_entity_next_to_the_dispatching_sensor():
    time_ent = {"entity_id": "time.octopus_energy_abc_intelligent_target_time", "state": "07:30:00", "attributes": {}}
    select_ent = {"entity_id": "select.octopus_energy_abc_intelligent_target_time", "state": "07:30",
                  "attributes": {"options": ["05:00", "05:30", "06:00"]}}
    other = {"entity_id": "time.octopus_energy_zzz_intelligent_target_time", "state": "08:00:00", "attributes": {}}
    assert target_time_entity([other, select_ent, time_ent], DISPATCH) is time_ent  # time preferred
    assert target_time_entity([other, select_ent], DISPATCH) is select_ent
    assert target_time_entity([other], DISPATCH) is None
    assert target_time_entity([time_ent], "sensor.x_smart_charging_schedule") is None  # E.ON: no setting
    assert allowed_times(select_ent) == ["05:00", "05:30", "06:00"]
    assert allowed_times(time_ent) == ALL_DAY_TIMES  # Octopus: any half hour
    assert allowed_times({"entity_id": "time.edf_energy_x_intelligent_target_time"}) == DEFAULT_TIMES


def test_octopus_any_time_of_day():
    allowed = ALL_DAY_TIMES
    assert len(allowed) == 48
    assert pick_ready_time(_at(5, 10), _at(5, 12), allowed) == _at(5, 12)
    assert pick_ready_time(_at(5, 16), _at(5, 22), allowed) == _at(5, 22)  # 4pm to 10pm now works
    assert pick_ready_time(_at(5, 16), _at(5, 22, 10), allowed) == _at(5, 22)
    assert pick_ready_time(_at(5, 21, 50), _at(5, 22, 10), allowed) == _at(5, 22)
    assert pick_ready_time(_at(5, 22, 5), _at(5, 22, 20), allowed) is None  # no half hour in between


def test_service_calls():
    t = _at(6, 7, 30)
    assert service_call({"entity_id": "time.x"}, t)["service_data"] == {"time": "07:30:00"}
    sel = service_call({"entity_id": "select.x"}, t)
    assert sel["domain"] == "select" and sel["service_data"] == {"option": "07:30"}


def _automation(now):
    a = Automation(None, now=lambda: now[0], clock=lambda: now[0].timestamp(),
                   localize=lambda naive: naive.replace(tzinfo=TZ))
    a.set_schedule(enabled=True, ready_time=True, entries=[
        {"time": t, "action": act, "days": list(range(7))}
        for t, act in (("02:00", "plug"), ("04:00", "unplug"), ("06:00", "plug"), ("08:00", "unplug"))])
    return a


def test_next_unplug_and_apply():
    now = [_at(5, 6, 0)]
    a = _automation(now)
    assert a.next_unplug(now[0]) == _at(5, 8)
    asked = []

    async def set_ready(unplug):
        asked.append(unplug)
        return {"unplug": unplug.isoformat(), "ready": "08:00", "entity_id": "time.x"}

    _run(apply_ready_time(a, set_ready))
    assert asked == [_at(5, 8)] and a.ready_status["ready"] == "08:00" and a.ready_status["at"]
    assert a.snapshot()["schedule"]["ready_status"]["ready"] == "08:00"
    a.entries = [e for e in a.entries if e["action"] == "plug"]
    _run(apply_ready_time(a, set_ready))
    assert "no unplug" in a.ready_status["error"]


def test_ready_time_saved(tmp_path):
    a = Automation(str(tmp_path))
    a.set_schedule(ready_time=True)
    assert Automation(str(tmp_path)).ready_time is True


def test_ha_link_sets_the_entity():
    from src.ha_link import HaLink
    from src.shared_state import SharedState

    async def noop(*a, **k):
        pass

    link = HaLink(None, SharedState(), lambda kw: None, noop, noop, token="t")
    sent = []
    states = [{"entity_id": DISPATCH, "state": "off", "attributes": {"planned_dispatches": []}},
              {"entity_id": "select.octopus_energy_abc_intelligent_target_time", "state": "07:00",
               "attributes": {"options": DEFAULT_TIMES}}]

    async def call(payload, timeout=15):
        sent.append(payload)
        return states if payload["type"] == "get_states" else None

    unplug = (datetime.datetime.now(TZ) + datetime.timedelta(days=1)).replace(hour=9, minute=10)
    assert "Not connected" in _run(link.set_ready_time(unplug))["error"]
    link._call = call
    link.dispatch_entities = [DISPATCH]
    out = _run(link.set_ready_time(unplug))
    assert out["ready"] == "09:00" and out["entity_id"].startswith("select.")
    assert sent[-1]["service"] == "select_option" and sent[-1]["service_data"] == {"option": "09:00"}
    link.dispatch_entities = []
    assert "wasn't found" in _run(link.set_ready_time(unplug))["error"]
