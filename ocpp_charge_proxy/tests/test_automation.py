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
    # (an unplug too, so 23:00 isn't inside a plugged-in stretch at start-up)
    a.set_schedule(enabled=True, entries=[{"time": "23:30", "action": "plug"}, {"time": "07:00", "action": "unplug"}])
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
    assert state.schedule_next["action"] == "unplug"  # 07:00 next
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


def test_octopus_six_hours_a_day():
    every = list(range(7))
    six = [{"time": "23:30", "action": "plug", "days": every}, {"time": "05:30", "action": "unplug", "days": every}]
    seven = [{"time": "23:30", "action": "plug", "days": every}, {"time": "06:30", "action": "unplug", "days": every}]
    a, clock = _automation()
    a.set_schedule(entries=seven, daily_cap_min=360)  # ready time off: no limit
    a.set_schedule(entries=six, ready_time=True, daily_cap_min=360)  # exactly 6 hours: fine
    try:
        a.set_schedule(entries=seven, daily_cap_min=360, provider="Octopus Energy")
        raise AssertionError("should have refused")
    except ValueError as err:
        assert "6 hours" in str(err) and "7h 00m" in str(err)
    assert a.entries[1]["time"] == "05:30"  # unchanged
    # Two 4-hour stretches 12 hours apart are 8 hours in 24
    split = [{"time": "00:00", "action": "plug", "days": every}, {"time": "04:00", "action": "unplug", "days": every},
             {"time": "12:00", "action": "plug", "days": every}, {"time": "16:00", "action": "unplug", "days": every}]
    try:
        a.set_schedule(entries=split, daily_cap_min=360)
        raise AssertionError("should have refused")
    except ValueError as err:
        assert "8h 00m" in str(err)
    a.set_schedule(entries=split)  # no cap (not Octopus): fine
    a.set_schedule(ready_time=False)
    a.set_schedule(entries=seven, daily_cap_min=360)  # ready time off again: fine
    try:
        a.set_schedule(ready_time=True, daily_cap_min=360)  # can't turn it on while over
        raise AssertionError("should have refused")
    except ValueError:
        assert a.ready_time is False
    a.set_schedule(enabled=False, daily_cap_min=360)  # switching off is always allowed
    assert a.schedule_enabled is False


def test_in_plug_window():
    every = list(range(7))
    a, clock = _automation(start=datetime.datetime(2026, 10, 6, 2, 0, tzinfo=TZ))  # Tuesday 02:00
    a.set_schedule(enabled=True, entries=[
        {"time": "23:30", "action": "plug", "days": every}, {"time": "07:00", "action": "unplug", "days": every}])
    assert a.in_plug_window().strftime("%a %H:%M") == "Mon 23:30"
    clock.advance(hours=6)  # 08:00: unplugged by then
    assert a.in_plug_window() is None
    a.set_schedule(enabled=False)
    clock.advance(hours=16)  # 00:00, inside again, but the schedule is off
    assert a.in_plug_window() is None


def test_startup_plugs_in_inside_a_scheduled_stretch():
    from src.automation import automation_loop
    from src.shared_state import SharedState
    every = list(range(7))

    def run(plugged_in, ready_results):
        a, clock = _automation(start=datetime.datetime(2026, 10, 6, 2, 0, tzinfo=TZ))
        a.set_schedule(enabled=True, ready_time=True, entries=[
            {"time": "23:30", "action": "plug", "days": every}, {"time": "07:00", "action": "unplug", "days": every}])
        state = SharedState(plugged_in=plugged_in)
        calls, asked = [], []

        async def plug(source=None):
            calls.append(("plug", source))
            state.plugged_in = True

        async def unplug(source=None):
            calls.append(("unplug", source))

        async def set_ready(unplug_at):
            asked.append(unplug_at)
            return ready_results.pop(0) if ready_results else {"ready": "07:00"}

        async def ticks():
            task = asyncio.ensure_future(automation_loop(a, state, plug, unplug, tick_s=0.01, set_ready_time=set_ready))
            await asyncio.sleep(0.1)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        _run(ticks())
        return a, calls, asked

    a, calls, asked = run(False, [{"error": "Not connected to Home Assistant"}])
    assert calls == [("plug", "schedule")]
    assert len(asked) == 2 and a.ready_status["ready"] == "07:00"  # tried again once HA was there
    assert a.last_run["startup"] is True
    _, calls, asked = run(True, [])  # already plugged in: nothing to do
    assert calls == [] and asked == []


# --- 2.9.0: one-off times and skips ---------------------------------------------


def test_one_off_time_runs_once_and_is_removed(tmp_path):
    a, clock = _automation(tmp_path)  # Monday 5 Oct 2026, 23:00
    a.set_schedule(enabled=True, entries=[{"time": "23:30", "action": "plug", "date": "2026-10-06"}])
    assert a.entries[0]["days"] == [1] and a.entries[0]["date"] == "2026-10-06"
    a.due()
    clock.advance(minutes=31)  # Monday 23:31: not today
    assert a.due() == []
    assert a.next_action()["time"].startswith("2026-10-06T23:30")
    clock.advance(days=1)  # Tuesday 23:31
    assert [e["action"] for e in a.due()] == ["plug"]
    clock.advance(days=1)  # a day later it's gone (and saved)
    a.due()
    assert a.entries == [] and Automation(str(tmp_path)).entries == []
    try:
        validate_entry({"time": "07:00", "action": "unplug", "date": "06/10/2026"})
        raise AssertionError("should have refused")
    except ValueError:
        pass


def test_skip_one_time(tmp_path):
    every = list(range(7))
    a, clock = _automation(tmp_path)  # Monday 23:00
    a.set_schedule(enabled=True, entries=[
        {"time": "23:30", "action": "plug", "days": every}, {"time": "07:00", "action": "unplug", "days": every}])
    plug_id = a.entries[0]["id"]
    a.set_skip(plug_id, "2026-10-05")  # tonight
    assert Automation(str(tmp_path)).skips == [{"entry_id": plug_id, "date": "2026-10-05"}]
    nxt = a.next_action()
    assert nxt["action"] == "unplug" and nxt["time"].startswith("2026-10-06T07:00")
    up = a.upcoming()
    assert up[0]["skipped"] is True and up[0]["action"] == "plug" and not up[1]["skipped"]
    a.due()
    clock.advance(minutes=31)
    assert a.due() == []  # skipped
    clock.advance(days=1)  # Tuesday 23:31: runs again
    assert [e["action"] for e in a.due()] == ["plug"]
    clock.advance(days=1)
    a.due()
    assert a.skips == []  # Monday's skip forgotten
    a.set_skip(plug_id, "2026-10-09")
    a.set_skip(plug_id, "2026-10-09", skip=False)  # undo
    assert a.skips == []
    try:
        a.set_skip("nope", "2026-10-07")
        raise AssertionError("should have refused")
    except ValueError:
        pass


def test_skipped_unplug_moves_the_ready_time_and_start_up():
    every = list(range(7))
    a, clock = _automation(start=datetime.datetime(2026, 10, 6, 2, 0, tzinfo=TZ))  # Tuesday 02:00
    a.set_schedule(enabled=True, entries=[
        {"time": "23:30", "action": "plug", "days": every}, {"time": "07:00", "action": "unplug", "days": every}])
    plug_id, unplug_id = a.entries[0]["id"], a.entries[1]["id"]
    a.set_skip(unplug_id, "2026-10-06")
    assert a.next_unplug(clock.now()).strftime("%a %H:%M") == "Wed 07:00"
    a.set_skip(plug_id, "2026-10-05")  # last night's plug-in skipped: not inside a stretch
    assert a.in_plug_window() is None


def test_skip_a_whole_slot():
    every = list(range(7))
    a, clock = _automation()  # Monday 23:00
    a.set_schedule(enabled=True, entries=[
        {"time": "23:30", "action": "plug", "days": every}, {"time": "07:00", "action": "unplug", "days": every}])
    plug_id, unplug_id = a.entries[0]["id"], a.entries[1]["id"]
    slot = [{"entry_id": plug_id, "date": "2026-10-05"}, {"entry_id": unplug_id, "date": "2026-10-06"}]
    a.set_skips(slot)
    nxt = a.next_action()
    assert nxt["action"] == "plug" and nxt["time"].startswith("2026-10-06T23:30")  # the whole night skipped
    try:
        a.set_skips(slot + [{"entry_id": "nope", "date": "2026-10-07"}], skip=False)  # all or nothing
        raise AssertionError("should have refused")
    except ValueError:
        assert len(a.skips) == 2
    a.set_skips(slot, skip=False)
    assert a.skips == []


def test_graceful_unplug_waits_for_the_supplier():
    from src import automation as auto_mod
    from src.automation import automation_loop
    every = list(range(7))

    def run(ready_time, in_session, supplier_stops):
        a, clock = _automation(start=datetime.datetime(2026, 10, 6, 6, 59, tzinfo=TZ))
        a.set_schedule(enabled=True, ready_time=ready_time, entries=[
            {"time": "23:30", "action": "plug", "days": every}, {"time": "07:00", "action": "unplug", "days": every}])
        state = SharedState(plugged_in=True, transaction_id=1 if in_session else None)
        calls = []

        async def plug(source=None):
            calls.append("plug")

        async def unplug(source=None):
            calls.append(("unplug", round(clock.epoch() - start)))
            state.plugged_in = False

        start = 0

        async def scenario():
            nonlocal start
            task = asyncio.ensure_future(automation_loop(a, state, plug, unplug, tick_s=0.01))
            await asyncio.sleep(0.03)
            clock.advance(minutes=1, seconds=1)  # 07:00:01: unplug due
            start = clock.epoch()
            await asyncio.sleep(0.05)
            waiting = a.unplug_at is not None
            if supplier_stops:
                clock.advance(seconds=20)
                state.transaction_id = None  # RemoteStop
            else:
                clock.advance(seconds=61)
            await asyncio.sleep(0.05)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            return waiting

        old = auto_mod.PENDING_TICK_S
        auto_mod.PENDING_TICK_S = 0.01
        try:
            waiting = _run(scenario())
        finally:
            auto_mod.PENDING_TICK_S = old
        return calls, waiting

    assert run(False, True, False) == ([("unplug", 0)], False)  # ready time off: straight away
    assert run(True, False, False) == ([("unplug", 0)], False)  # no session: straight away
    assert run(True, True, True) == ([("unplug", 20)], True)  # supplier stopped it after 20 s
    assert run(True, True, False) == ([("unplug", 61)], True)  # gave it a minute


def test_unplug_wait_setting(tmp_path):
    a, _ = _automation(tmp_path)
    assert a.unplug_wait_s == 60 and a.snapshot()["schedule"]["unplug_wait_s"] == 60
    a.set_schedule(unplug_wait_s=120)
    assert _automation(tmp_path)[0].unplug_wait_s == 120  # saved
    for bad in (-1, 601, "x"):
        try:
            a.set_schedule(unplug_wait_s=bad)
            raise AssertionError("accepted %r" % (bad,))
        except ValueError:
            pass
    assert a.unplug_wait_s == 120


def test_unplug_wait_zero_unplugs_straight_away():
    every = list(range(7))
    a, clock = _automation(start=datetime.datetime(2026, 10, 6, 6, 59, tzinfo=TZ))
    a.set_schedule(enabled=True, ready_time=True, unplug_wait_s=0, entries=[
        {"time": "23:30", "action": "plug", "days": every}, {"time": "07:00", "action": "unplug", "days": every}])
    state = SharedState(plugged_in=True, transaction_id=1)
    calls = []

    async def plug(source=None):
        calls.append("plug")

    async def unplug(source=None):
        calls.append("unplug")
        state.plugged_in = False

    async def scenario():
        task = asyncio.ensure_future(automation_loop(a, state, plug, unplug, tick_s=0.01))
        await asyncio.sleep(0.03)
        clock.advance(minutes=1, seconds=1)
        await asyncio.sleep(0.05)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    _run(scenario())
    assert calls == ["unplug"] and a.unplug_at is None
