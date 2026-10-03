import asyncio
import datetime
import json

import pytest

from src.automation import Automation, ReplugOptions, automation_loop, validate_entry
from src.shared_state import SharedState

TZ = datetime.timezone.utc


class Clock:
    """Fake local time (UTC here) and epoch clock moving together."""

    def __init__(self, start: datetime.datetime):
        self.dt = start

    def now(self):
        return self.dt

    def epoch(self):
        return self.dt.timestamp()

    def advance(self, **kw):
        self.dt += datetime.timedelta(**kw)


def _automation(tmp_path=None, options=ReplugOptions(), start=datetime.datetime(2026, 10, 5, 23, 0, tzinfo=TZ)):
    clock = Clock(start)  # Monday 5 Oct 2026
    a = Automation(str(tmp_path) if tmp_path else None, options, now=clock.now, clock=clock.epoch,
                   localize=lambda naive: naive.replace(tzinfo=TZ))
    return a, clock


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# --- entries -----------------------------------------------------------------


def test_validate_entry():
    e = validate_entry({"time": "7:05", "action": "unplug", "days": [4, 0, 0]})
    assert e["time"] == "07:05" and e["days"] == [0, 4] and e["enabled"] is True and e["id"]
    assert validate_entry({"time": "23:30", "action": "plug"})["days"] == list(range(7))
    for bad in ({"time": "24:00", "action": "plug"}, {"time": "x", "action": "plug"},
                {"time": "10:00", "action": "toggle"}, {"time": "10:00", "action": "plug", "days": []},
                {"time": "10:00", "action": "plug", "days": [7]}):
        with pytest.raises(ValueError):
            validate_entry(bad)


# --- schedule ----------------------------------------------------------------


def test_due_fires_once_at_the_time():
    a, clock = _automation()
    a.set_schedule(enabled=True, entries=[
        {"time": "23:30", "action": "plug", "days": [0, 1, 2, 3, 4]},
        {"time": "07:00", "action": "unplug"},
    ])
    assert a.due() == []  # first check only sets the starting point
    clock.advance(minutes=29)
    assert a.due() == []
    clock.advance(seconds=75)  # 23:30:15
    assert [e["action"] for e in a.due()] == ["plug"]
    clock.advance(seconds=15)
    assert a.due() == []  # not again
    clock.advance(hours=7, minutes=29)  # Tue 06:59:30
    assert a.due() == []
    clock.advance(seconds=45)  # 07:00:15
    assert [e["action"] for e in a.due()] == ["unplug"]


def test_schedule_respects_days_and_disabled():
    a, clock = _automation(start=datetime.datetime(2026, 10, 10, 23, 29, tzinfo=TZ))  # Saturday
    a.set_schedule(enabled=True, entries=[{"time": "23:30", "action": "plug", "days": [0, 1, 2, 3, 4]}])
    a.due()
    clock.advance(minutes=2)
    assert a.due() == []  # weekdays only
    a.set_schedule(enabled=False)
    assert a.next_action() is None


def test_missed_times_are_not_caught_up_after_a_long_gap():
    a, clock = _automation()
    a.set_schedule(enabled=True, entries=[{"time": "23:30", "action": "plug"}])
    a.due()
    clock.advance(hours=2)  # stopped / asleep through 23:30
    assert a.due() == []


def test_next_action():
    a, clock = _automation()  # Monday 23:00
    a.set_schedule(enabled=True, entries=[
        {"time": "07:00", "action": "unplug", "days": [1]},
        {"time": "23:30", "action": "plug", "days": [0]},
        {"time": "22:00", "action": "plug", "enabled": False},
    ])
    nxt = a.next_action()
    assert nxt["action"] == "plug" and nxt["time"].startswith("2026-10-05T23:30")
    clock.advance(minutes=31)
    assert a.next_action()["time"].startswith("2026-10-06T07:00")


def test_schedule_saved(tmp_path):
    a, _ = _automation(tmp_path)
    a.set_schedule(enabled=True, entries=[{"time": "23:30", "action": "plug"}])
    b, _ = _automation(tmp_path)
    assert b.schedule_enabled is True and b.entries[0]["time"] == "23:30"


def test_bad_schedule_rejected_and_unchanged(tmp_path):
    a, _ = _automation(tmp_path)
    a.set_schedule(entries=[{"time": "23:30", "action": "plug"}])
    with pytest.raises(ValueError):
        a.set_schedule(entries=[{"time": "99:00", "action": "plug"}])
    assert len(a.entries) == 1


# --- re-plug -----------------------------------------------------------------


def test_replug_after_wait_up_to_the_limit():
    a, clock = _automation(options=ReplugOptions(True, 10, 2))
    assert not a.replug_due(True, False, True)  # starts the wait
    clock.advance(minutes=9)
    assert not a.replug_due(True, False, True)
    assert a.replug_status()["status"] == "waiting"
    clock.advance(minutes=1)
    assert a.replug_due(True, False, True)

    calls = []

    async def unplug(source=None):
        calls.append("unplug")

    async def plug(source=None):
        calls.append("plug")

    _run(a.run_replug(unplug, plug, wait_s=0))
    assert calls == ["unplug", "plug"] and a.attempts_used == 1
    assert not a.replug_due(True, False, True)  # waits again from the re-plug
    clock.advance(minutes=10)
    assert a.replug_due(True, False, True)
    _run(a.run_replug(unplug, plug, wait_s=0))
    clock.advance(minutes=10)
    assert not a.replug_due(True, False, True)  # 2 tries used: give up
    assert a.replug_status()["status"] == "gave_up"


def test_replug_resets_when_session_starts_or_unplugged():
    a, clock = _automation()
    a.replug_due(True, False, True)
    a.attempts_used = 3
    a.gave_up = True
    assert not a.replug_due(True, True, True)  # session started
    assert a.attempts_used == 0 and not a.gave_up and a.replug_status()["status"] == "idle"
    a.attempts_used = 2
    assert not a.replug_due(False, False, True)  # unplugged
    assert a.attempts_used == 0


def test_replug_waits_only_while_online_and_enabled():
    a, clock = _automation()
    a.replug_due(True, False, True)
    clock.advance(minutes=9)
    assert not a.replug_due(True, False, False)  # offline: the wait restarts
    clock.advance(minutes=5)
    assert not a.replug_due(True, False, True)
    clock.advance(minutes=10)
    assert a.replug_due(True, False, True)
    a.set_replug(enabled=False)
    assert not a.replug_due(True, False, True)
    assert a.replug_status()["status"] == "off"


def test_replug_settings_saved_win_over_defaults(tmp_path):
    a, _ = _automation(tmp_path, ReplugOptions(True, 10, 3))
    assert a.replug["after_min"] == 10  # nothing saved: the defaults
    a.set_replug(after_min=15, attempts=5)
    b, _ = _automation(tmp_path, ReplugOptions(True, 20, 3))
    assert (b.replug["after_min"], b.replug["attempts"]) == (15, 5)


def test_replug_settings_validated():
    a, _ = _automation()
    for bad in ({"after_min": 0}, {"attempts": -1}, {"after_min": "x"}):
        with pytest.raises(ValueError):
            a.set_replug(**bad)


# --- the loop ----------------------------------------------------------------


def test_loop_runs_schedule_and_publishes():
    a, clock = _automation()
    a.set_schedule(enabled=True, entries=[{"time": "23:30", "action": "plug"}])
    state = SharedState(connected_to_server=True)
    calls = []

    async def plug(source=None):
        calls.append("plug")
        state.plugged_in = True
        state.state = "Preparing"

    async def unplug(source=None):
        calls.append("unplug")

    async def scenario():
        task = asyncio.ensure_future(automation_loop(a, state, plug, unplug, tick_s=0.01))
        await asyncio.sleep(0.03)
        clock.advance(minutes=30)
        await asyncio.sleep(0.05)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    _run(scenario())
    assert calls == ["plug"]
    assert state.schedule_enabled is True
    assert state.replug["status"] == "waiting"
    assert state.schedule_next["action"] == "plug"
    json.dumps(state.to_dict())  # serialisable for the API


def test_no_replug_while_supplier_has_a_slot_planned():
    a, clock = _automation(options=ReplugOptions(True, 10, 3))
    assert not a.replug_due(True, False, True, scheduled=False)  # plugged in, nothing planned yet
    clock.advance(minutes=5)
    # Octopus plans a slot for tonight: no re-plug, however long until it starts
    assert not a.replug_due(True, False, True, scheduled=True)
    assert a.replug_status()["status"] == "scheduled"
    clock.advance(hours=3)
    assert not a.replug_due(True, False, True, scheduled=True)
    # The plan is dropped: the wait starts again from now
    assert not a.replug_due(True, False, True, scheduled=False)
    assert a.replug_status()["status"] == "waiting"
    clock.advance(minutes=10)
    assert a.replug_due(True, False, True, scheduled=False)


def test_replug_without_supplier_info_waits_for_a_session():
    a, clock = _automation(options=ReplugOptions(True, 10, 3))
    a.replug_due(True, False, True, scheduled=None)
    clock.advance(minutes=10)
    assert a.replug_due(True, False, True, scheduled=None)


def test_automation_loop_publishes_scheduled():
    from src.automation import automation_loop
    from src.shared_state import SharedState, display_status
    a, clock = _automation()
    state = SharedState(state="Preparing", plugged_in=True, connected_to_server=True)

    async def noop(source=None):
        pass

    async def one_tick():
        task = asyncio.ensure_future(automation_loop(a, state, noop, noop, tick_s=60, scheduled=lambda: True))
        await asyncio.sleep(0.05)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    _run(one_tick())
    assert state.scheduled is True and display_status(state) == "Scheduled"
    assert state.replug["status"] == "scheduled"
    state.state = "Charging"
    assert display_status(state) == "Charging"
