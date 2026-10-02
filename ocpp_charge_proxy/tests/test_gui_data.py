import json

from src.gui_data import Health, MessageLog, PowerHistory, SessionLog
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
