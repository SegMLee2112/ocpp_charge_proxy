import json

from src.gui_data import DailyEnergy, Health, MessageLog, PowerHistory, SessionLog
from src.shared_state import SharedState


def test_message_log_pairs_replies_with_their_call():
    log = MessageLog()
    log.record(json.dumps([2, "a1", "ChangeConfiguration", {"key": "minSoC", "value": "25"}]), incoming=True)
    log.record(json.dumps([3, "a1", {"status": "Accepted"}]), incoming=False)
    log.record(json.dumps([4, "b2", "NotImplemented", "nope", {}]), incoming=True)
    entries = log.since(0)
    assert [e["type"] for e in entries] == ["call", "result", "error"]
    assert entries[0]["direction"] == "received" and entries[0]["summary"] == "minSoC = 25"
    assert entries[1]["action"] == "ChangeConfiguration" and entries[1]["direction"] == "sent"
    assert entries[2]["payload"]["errorCode"] == "NotImplemented"
    assert [e["seq"] for e in log.since(1)] == [2, 3]


def test_message_log_keeps_the_newest_and_ignores_junk():
    log = MessageLog(size=3)
    for i in range(5):
        log.record([2, str(i), "Heartbeat", {}], incoming=False)
    log.record("not json", incoming=True)
    assert [e["message_id"] for e in log.since(0)] == ["2", "3", "4"]
    assert log.last_seq == 5


def test_sessions_survive_a_restart(tmp_path):
    log = SessionLog(str(tmp_path))
    log.start(1, "TAG", 1000, "2026-10-02T15:00:00Z")
    log.sample(1.2)
    log.sample(1.4)
    log.stop(3500, "Remote", "2026-10-02T16:30:00Z")
    again = SessionLog(str(tmp_path))
    assert again.current is None
    s = again.history[0]
    assert s["energy_kwh"] == 2.5 and s["duration_s"] == 5400
    assert s["peak_power_kw"] == 1.4 and s["reason"] == "Remote"


def test_running_session_saved_and_snapshot_live(tmp_path):
    log = SessionLog(str(tmp_path))
    log.start(-5, "TAG", 1000)
    log.remap_transaction_id(-5, 7)
    again = SessionLog(str(tmp_path))
    assert again.current["transaction_id"] == 7
    snap = again.snapshot(energy_register_wh=1750)
    assert snap["current"]["energy_kwh"] == 0.75 and snap["current"]["duration_s"] >= 0


def test_history_is_capped(tmp_path):
    log = SessionLog(str(tmp_path), size=2)
    for i in range(3):
        log.start(i, "T", 0)
        log.stop(1000, "Remote")
    assert [s["transaction_id"] for s in log.history] == [2, 1]


def test_session_log_without_disk():
    log = SessionLog(None)
    log.start(1, "T", 0)
    log.stop(10, None)
    assert log.history[0]["reason"] is None


def test_power_history_since():
    now = [100.0]
    history = PowerHistory(size=3, clock=lambda: now[0])
    state = SharedState(power_kw=1.37, current_a=6.0, soc_percent=55)
    for _ in range(4):
        history.sample(state)
        now[0] += 10
    assert [s["t"] for s in history.since(0)] == [110.0, 120.0, 130.0]
    assert [s["t"] for s in history.since(115)] == [120.0, 130.0]
    assert history.since(0)[0]["soc"] == 55


def test_health_counts_reconnects():
    now = [1000.0]
    health = Health(version="1.1.0", clock=lambda: now[0])
    health.disconnected("refused")  # before ever connecting: not a drop
    health.connected()
    now[0] += 60
    health.disconnected("timeout")
    health.connected()
    now[0] += 5
    snap = health.snapshot()
    assert snap["version"] == "1.1.0" and snap["uptime_s"] == 65
    assert snap["reconnects"] == 1 and snap["disconnects"] == 1
    assert snap["connected_for_s"] == 5 and snap["last_disconnect"]["reason"] == "timeout"


def test_plug_in_without_session_recorded(tmp_path):
    log = SessionLog(str(tmp_path))
    log.plugged(True, "schedule", "2026-10-02T22:30:00Z")
    assert SessionLog(str(tmp_path)).plug["plugged_by"] == "schedule"  # survives a restart
    log.plugged(False, "auto re-plug", "2026-10-02T22:40:00Z")
    entry = log.history[0]
    assert entry["type"] == "no_session" and entry["reason"] == "replugged"
    assert entry["duration_s"] == 600 and entry["plugged_by"] == "schedule"
    assert entry["unplugged_by"] == "auto re-plug" and log.plug is None


def test_plug_in_that_gets_a_session_is_not_recorded_as_failed(tmp_path):
    log = SessionLog(str(tmp_path))
    log.plugged(True, "web page")
    log.start(1, "TAG", 0)
    log.stop(1000, "Remote")
    log.plugged(False, "web page")
    assert [e.get("type") for e in log.history] == [None]


def test_no_session_entries_kept_separately(tmp_path):
    log = SessionLog(str(tmp_path), size=2)
    log.start(1, "T", 0)
    log.stop(10, "Remote")
    for _ in range(3):
        log.plugged(True, "web page")
        log.plugged(False, "web page")
    kinds = [e.get("type", "session") for e in log.history]
    assert kinds.count("no_session") == 2 and kinds.count("session") == 1
    snap = log.snapshot()
    assert snap["waiting"] is None
    log.plugged(True, "Home Assistant")
    assert log.snapshot()["waiting"]["plugged_by"] == "Home Assistant"


def test_message_log_kept_across_restarts(tmp_path):
    log = MessageLog(data_dir=str(tmp_path))
    log.record('[2,"a","Heartbeat",{}]', incoming=False)
    log.record('[3,"a",{"currentTime":"2026-10-02T15:00:00Z"}]', incoming=True)
    log.save()
    again = MessageLog(data_dir=str(tmp_path))
    entries = again.since(0)
    assert [e["type"] for e in entries] == ["call", "result", "restart"]
    assert again.last_seq == 3
    again.record('[2,"b","Heartbeat",{}]', incoming=False)
    assert again.since(3)[0]["seq"] == 4  # numbering carries on


def test_message_log_saves_only_when_changed(tmp_path):
    log = MessageLog(data_dir=str(tmp_path))
    log.save()
    assert not (tmp_path / "messages.json").exists()  # nothing to save
    log.record('[2,"a","Heartbeat",{}]', incoming=False)
    log.save()
    assert (tmp_path / "messages.json").exists()
    assert MessageLog(data_dir=str(tmp_path / "empty")).since(0) == []


def test_chart_history_kept_across_restarts(tmp_path):
    now = [10_000.0]
    history = PowerHistory(clock=lambda: now[0], data_dir=str(tmp_path))
    history.sample(SharedState(power_kw=1.4))
    history.save()
    again = PowerHistory(clock=lambda: now[0], data_dir=str(tmp_path))
    assert [s["power_kw"] for s in again.since(0)] == [1.4]
    now[0] += 25 * 3600  # older than the 10 s window: dropped
    assert PowerHistory(clock=lambda: now[0], data_dir=str(tmp_path)).since(0) == []


def test_daily_energy(tmp_path):
    import datetime
    day = [datetime.date(2026, 10, 1)]
    daily = DailyEnergy(str(tmp_path), today=lambda: day[0])
    daily.update(6600.0)
    daily.update(6607.5)
    day[0] = datetime.date(2026, 10, 2)
    daily.update(6608.0)  # yesterday's last reading starts today
    daily.update(6610.0)
    daily.save()
    again = DailyEnergy(str(tmp_path), today=lambda: day[0])
    snap = again.snapshot(3)
    assert [d["date"] for d in snap] == ["2026-09-30", "2026-10-01", "2026-10-02"]
    assert [d["kwh"] for d in snap] == [0.0, 7.5, 2.5]
    again.update(0)  # ignored
    assert again.snapshot(1)[0]["kwh"] == 2.5


def test_daily_energy_filled_in_from_sessions(tmp_path):
    import datetime
    today = datetime.date.today()
    daily = DailyEnergy(str(tmp_path), today=lambda: today)
    daily.update(6619.83)  # tracking only started now (e.g. just updated)
    start = datetime.datetime.combine(today, datetime.time(12, 0)).astimezone().isoformat()
    sessions = [
        {"start": start, "energy_kwh": 0.52},
        {"start": start, "type": "no_session"},
    ]
    assert daily.snapshot(1, sessions)[0]["kwh"] == 0.52
    daily.update(6625.83)  # 6 kWh metered today: more than the sessions
    assert daily.snapshot(1, sessions)[0]["kwh"] == 6.0



def test_long_history_averages_two_minutes():
    from src.gui_data import LONG_SAMPLE_S
    now = [1_200_000.0]  # the start of a 2-minute slot
    history = PowerHistory(clock=lambda: now[0])
    state = SharedState(power_kw=0.0, state="Preparing")
    for i in range(LONG_SAMPLE_S // 10 + 1):  # one full slot, then the next begins
        state.power_kw = 7.0 if i == 3 else 1.0
        state.state = "Charging" if i == 3 else "Preparing"
        history.sample(state)
        now[0] += 10
    (avg,) = history.long_since(0)
    assert avg["t"] == 1_200_000.0 + LONG_SAMPLE_S / 2
    assert avg["power_kw"] == round((11 * 1.0 + 7.0) / 12, 3)
    assert avg["power_max_kw"] == 7.0
    assert avg["state"] == "Charging"  # the most telling state in the slot
    assert history.long_since(avg["t"]) == []


def test_long_history_kept_and_filled_in_from_short(tmp_path):
    now = [1_200_000.0]
    history = PowerHistory(clock=lambda: now[0], data_dir=str(tmp_path))
    for _ in range(30):  # 5 minutes: two full slots and part of a third
        history.sample(SharedState(power_kw=2.0))
        now[0] += 10
    history.save()
    assert len(history.long_since(0)) == 2
    # The slot in progress at the stop is filled in from the 10 s samples
    again = PowerHistory(clock=lambda: now[0], data_dir=str(tmp_path))
    assert len(again.long_since(0)) == 2
    again.sample(SharedState(power_kw=2.0))
    now[0] += 120
    again.sample(SharedState(power_kw=2.0))
    assert len(again.long_since(0)) == 3
    # Kept for 14 days, after the 10 s samples have gone
    again.save()
    now[0] += 3 * 86400
    later = PowerHistory(clock=lambda: now[0], data_dir=str(tmp_path))
    assert later.since(0) == [] and len(later.long_since(0)) == 3
    now[0] += 12 * 86400
    assert PowerHistory(clock=lambda: now[0], data_dir=str(tmp_path)).long_since(0) == []


def test_long_history_built_from_old_short_history(tmp_path):
    """First start after updating: the 10 s history already on disk is averaged."""
    import json
    samples = [{"t": 1_200_000.0 + i * 10, "power_kw": 3.0, "current_a": 13.0, "soc": None,
                "max_amps": 16, "effective_amps": 13, "provider_limit_amps": None, "state": "Charging"}
               for i in range(36)]
    (tmp_path / "history.json").write_text(json.dumps(samples))
    history = PowerHistory(clock=lambda: 1_200_400.0, data_dir=str(tmp_path))
    assert [s["power_kw"] for s in history.long_since(0)] == [3.0, 3.0]
    history.save()
    assert (tmp_path / "history_long.json").exists()
