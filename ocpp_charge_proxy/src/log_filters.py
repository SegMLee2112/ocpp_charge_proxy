"""Logging filters for the ocpp library's message log."""

from __future__ import annotations

import json
import logging

# OCPP actions whose send/receive lines are routine noise at INFO
DEBUG_ONLY_ACTIONS = frozenset({"Heartbeat"})


class DemoteRoutineMessages(logging.Filter):
    """Show the ocpp library's Heartbeat lines at DEBUG instead of INFO.

    The library logs every frame at INFO ("send [...]" / "receive message
    [...]"). This catches Heartbeat calls and the server's reply to them
    (matched by message id) and re-labels them DEBUG: they're dropped unless
    log_level is debug. Every other message is untouched.
    """

    def __init__(self, actions=DEBUG_ONLY_ACTIONS) -> None:
        super().__init__()
        self._actions = frozenset(actions)
        self._pending: set[str] = set()  # ids of heartbeats awaiting a reply

    def _is_routine(self, record: logging.LogRecord) -> bool:
        raw = record.args[-1] if isinstance(record.args, tuple) and record.args else None
        if not isinstance(raw, (str, bytes)):
            return False
        try:
            frame = json.loads(raw)
            kind, uid = frame[0], frame[1]
        except (ValueError, TypeError, IndexError, KeyError):
            return False
        if kind == 2 and len(frame) > 2 and frame[2] in self._actions:
            if len(self._pending) > 100:  # replies that never came
                self._pending.clear()
            self._pending.add(uid)
            return True
        if kind in (3, 4) and uid in self._pending:
            self._pending.discard(uid)
            return True
        return False

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno != logging.INFO or not self._is_routine(record):
            return True
        # The add-on's log_level is set on the root logger (basicConfig).
        # getEffectiveLevel, not isEnabledFor, which caches its answer.
        if logging.getLogger().getEffectiveLevel() > logging.DEBUG:
            return False
        record.levelno = logging.DEBUG
        record.levelname = logging.getLevelName(logging.DEBUG)
        return True


def install() -> None:
    logging.getLogger("ocpp").addFilter(DemoteRoutineMessages())
