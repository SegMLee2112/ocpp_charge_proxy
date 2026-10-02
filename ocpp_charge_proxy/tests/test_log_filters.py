import json
import logging

from src.log_filters import DemoteRoutineMessages


def _record(direction: str, frame: list) -> logging.LogRecord:
    # Same shape as the ocpp library's log calls: "%s: send %s" / "%s: receive message %s"
    fmt = "%s: send %s" if direction == "send" else "%s: receive message %s"
    return logging.LogRecord("ocpp", logging.INFO, __file__, 1, fmt, ("CP1", json.dumps(frame)), None)


def test_heartbeat_and_reply_hidden_at_info(monkeypatch):
    monkeypatch.setattr(logging.getLogger(), "level", logging.INFO)
    f = DemoteRoutineMessages()
    assert f.filter(_record("send", [2, "hb1", "Heartbeat", {}])) is False
    assert f.filter(_record("receive", [3, "hb1", {"currentTime": "2026-10-02T12:00:00Z"}])) is False


def test_heartbeat_shown_as_debug_when_debugging(monkeypatch):
    monkeypatch.setattr(logging.getLogger(), "level", logging.DEBUG)
    f = DemoteRoutineMessages()
    rec = _record("send", [2, "hb2", "Heartbeat", {}])
    assert f.filter(rec) is True
    assert rec.levelname == "DEBUG"


def test_other_messages_untouched(monkeypatch):
    monkeypatch.setattr(logging.getLogger(), "level", logging.INFO)
    f = DemoteRoutineMessages()
    for rec in (
        _record("send", [2, "s1", "StatusNotification", {"connectorId": 1}]),
        _record("receive", [3, "s1", {}]),  # reply to a non-heartbeat
        _record("receive", [2, "r1", "RemoteStartTransaction", {"idTag": "x"}]),
        _record("send", [3, "b1", {"currentTime": "t", "interval": 10, "status": "Accepted"}]),
    ):
        assert f.filter(rec) is True
        assert rec.levelname == "INFO"


def test_unparseable_lines_untouched(monkeypatch):
    monkeypatch.setattr(logging.getLogger(), "level", logging.INFO)
    f = DemoteRoutineMessages()
    rec = logging.LogRecord("ocpp", logging.INFO, __file__, 1, "something else", (), None)
    assert f.filter(rec) is True
