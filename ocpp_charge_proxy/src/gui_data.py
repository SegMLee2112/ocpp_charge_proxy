"""Data kept for the web GUI only (not pushed to Home Assistant).

- MessageLog: the last few hundred OCPP frames, both ways, in full.
- SessionLog: the current charging session and the last few finished ones
  (saved to disk, so the history survives a restart).
- PowerHistory: power / current / SoC samples for the chart (memory only).
- Health: uptime, connection history and version.

Display only: recording never raises into the charger.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Optional

from src.traffic import summarise_command

logger = logging.getLogger(__name__)

MESSAGE_LOG_SIZE = 300
SESSION_HISTORY_SIZE = 20
HISTORY_SAMPLE_S = 10
HISTORY_HOURS = 6


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(value) -> Optional[datetime.datetime]:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=datetime.timezone.utc)


# --- OCPP message log --------------------------------------------------------


class MessageLog:
    """Every OCPP frame, newest last, numbered so the GUI can ask for new ones."""

    def __init__(self, size: int = MESSAGE_LOG_SIZE) -> None:
        self._entries: deque[dict] = deque(maxlen=size)
        self._seq = 0
        self._actions: dict[str, str] = {}  # uid -> action of the call it answers

    @property
    def last_seq(self) -> int:
        return self._seq

    def record(self, raw, incoming: bool) -> None:
        try:
            msg = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
            kind, uid = msg[0], str(msg[1])
            if kind == 2:
                action = msg[2]
                payload = msg[3] if len(msg) > 3 else {}
                if len(self._actions) >= 500:
                    self._actions.pop(next(iter(self._actions)))
                self._actions[uid] = action
                entry_type = "call"
            elif kind == 3:
                action = self._actions.pop(uid, None)
                payload = msg[2] if len(msg) > 2 else {}
                entry_type = "result"
            elif kind == 4:
                action = self._actions.pop(uid, None)
                payload = {
                    "errorCode": msg[2] if len(msg) > 2 else "",
                    "errorDescription": msg[3] if len(msg) > 3 else "",
                    "errorDetails": msg[4] if len(msg) > 4 else {},
                }
                entry_type = "error"
            else:
                return
            self._seq += 1
            self._entries.append({
                "seq": self._seq,
                "timestamp": _now_iso(),
                "direction": "received" if incoming else "sent",
                "type": entry_type,
                "message_id": uid,
                "action": action,
                "summary": summarise_command(action, payload) if entry_type == "call" else "",
                "payload": payload,
            })
        except Exception:
            logger.debug("Could not log OCPP frame", exc_info=True)

    def since(self, after: int = 0, limit: int = MESSAGE_LOG_SIZE) -> list[dict]:
        newer = [e for e in self._entries if e["seq"] > after]
        return newer[-limit:]


# --- Charging sessions -------------------------------------------------------


class SessionLog:
    """The current session and recent finished ones, saved in sessions.json.

    The current session is saved too, so one cut short by a power cut is
    still closed (reason PowerLoss) after the restart.
    """

    def __init__(self, data_dir: Optional[str], size: int = SESSION_HISTORY_SIZE) -> None:
        self._path = os.path.join(data_dir, "sessions.json") if data_dir else None
        self._size = size
        self.current: Optional[dict] = None
        self.history: list[dict] = []  # newest first
        self._load()

    def _load(self) -> None:
        if not self._path:
            return
        for path in (self._path, self._path + ".bak"):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                current = data.get("current")
                self.current = current if isinstance(current, dict) else None
                self.history = [s for s in data.get("history") or [] if isinstance(s, dict)][: self._size]
                return
            except FileNotFoundError:
                continue
            except Exception:
                logger.warning("Session history %s is unreadable", path)

    def _save(self) -> None:
        if not self._path:
            return
        try:
            tmp = self._path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"current": self.current, "history": self.history}, f)
                f.flush()
                os.fsync(f.fileno())
            if os.path.exists(self._path):
                os.replace(self._path, self._path + ".bak")
            os.replace(tmp, self._path)
        except Exception:
            logger.warning("Could not save session history", exc_info=True)

    def start(self, transaction_id, id_tag, meter_start_wh: int, timestamp: Optional[str] = None) -> None:
        self.current = {
            "transaction_id": transaction_id,
            "id_tag": id_tag,
            "start": timestamp or _now_iso(),
            "meter_start_wh": int(meter_start_wh),
            "peak_power_kw": 0.0,
        }
        self._save()

    def remap_transaction_id(self, old, new) -> None:
        """A held StartTransaction was accepted: use the server's id."""
        changed = False
        for session in ([self.current] if self.current else []) + self.history:
            if session.get("transaction_id") == old:
                session["transaction_id"] = new
                changed = True
        if changed:
            self._save()

    def sample(self, power_kw: float) -> None:
        """Track the session's peak power (saved at the stop, not every sample)."""
        if self.current is not None and power_kw > self.current.get("peak_power_kw", 0.0):
            self.current["peak_power_kw"] = round(power_kw, 2)

    def stop(self, meter_stop_wh: int, reason, timestamp: Optional[str] = None, transaction_id=None) -> None:
        if self.current is None:
            return
        session = dict(self.current)
        session["stop"] = timestamp or _now_iso()
        session["meter_stop_wh"] = int(meter_stop_wh)
        session["energy_kwh"] = round(max(0, int(meter_stop_wh) - session["meter_start_wh"]) / 1000.0, 3)
        session["reason"] = str(getattr(reason, "value", reason)) if reason else None
        if transaction_id is not None:
            session["transaction_id"] = transaction_id
        start, stop = _parse_iso(session["start"]), _parse_iso(session["stop"])
        session["duration_s"] = int((stop - start).total_seconds()) if start and stop else None
        self.history.insert(0, session)
        del self.history[self._size:]
        self.current = None
        self._save()

    def snapshot(self, energy_register_wh: Optional[int] = None) -> dict:
        current = None
        if self.current is not None:
            current = dict(self.current)
            if energy_register_wh is not None:
                current["energy_kwh"] = round(
                    max(0, energy_register_wh - current["meter_start_wh"]) / 1000.0, 3,
                )
            start = _parse_iso(current["start"])
            if start:
                current["duration_s"] = int(
                    (datetime.datetime.now(datetime.timezone.utc) - start).total_seconds()
                )
        return {"current": current, "history": list(self.history)}


# --- Power history for the chart ---------------------------------------------


class PowerHistory:
    """Samples every HISTORY_SAMPLE_S seconds for the last HISTORY_HOURS hours."""

    def __init__(self, size: int = HISTORY_HOURS * 3600 // HISTORY_SAMPLE_S,
                 clock: Callable[[], float] = time.time) -> None:
        self._samples: deque[dict] = deque(maxlen=size)
        self._clock = clock

    def sample(self, state) -> dict:
        entry = {
            "t": round(self._clock(), 1),
            "power_kw": round(float(state.power_kw or 0.0), 3),
            "current_a": round(float(state.current_a or 0.0), 2),
            "soc": state.soc_percent,
            "max_amps": state.current_amps_setting,
            "effective_amps": state.current_amps_effective,
            "provider_limit_amps": state.current_amps_provider_limit,
            "state": str(state.state),
        }
        self._samples.append(entry)
        return entry

    def since(self, after: float = 0.0) -> list[dict]:
        return [s for s in self._samples if s["t"] > after]


@dataclass
class GuiSources:
    """Everything the GUI endpoints read, handed to the API in one go."""

    message_log: MessageLog
    history: PowerHistory
    sessions: Callable[[], dict]
    provider: Callable[[], dict]
    health: Callable[[], dict]


async def sample_loop(history: PowerHistory, shared_state, refresh: Optional[Callable[[], None]] = None,
                      on_sample: Optional[Callable[[dict], None]] = None,
                      interval: float = HISTORY_SAMPLE_S) -> None:
    """Record a chart sample every `interval` seconds, for the life of the add-on."""
    import asyncio
    while True:
        try:
            if refresh is not None:
                refresh()
            entry = history.sample(shared_state)
            if on_sample is not None:
                on_sample(entry)
        except Exception:
            logger.debug("History sample failed", exc_info=True)
        await asyncio.sleep(interval)


# --- Health ------------------------------------------------------------------


class Health:
    """Add-on uptime and connection history."""

    def __init__(self, version: Optional[str] = None, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self.version = version or os.environ.get("ADDON_VERSION") or "dev"
        self.started = self._clock()
        self.connected_since: Optional[float] = None
        self.connects = 0
        self.disconnects = 0
        self.last_disconnect: Optional[dict] = None

    def connected(self) -> None:
        self.connects += 1
        self.connected_since = self._clock()

    def disconnected(self, reason: str) -> None:
        if self.connected_since is not None:
            self.disconnects += 1
        self.connected_since = None
        self.last_disconnect = {
            "timestamp": _now_iso(),
            "reason": reason or "unknown",
        }

    def snapshot(self) -> dict:
        now = self._clock()
        return {
            "version": self.version,
            "started": datetime.datetime.fromtimestamp(self.started, datetime.timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
            "uptime_s": int(now - self.started),
            "connected_for_s": None if self.connected_since is None else int(now - self.connected_since),
            "connects": self.connects,
            "reconnects": max(0, self.connects - 1),
            "disconnects": self.disconnects,
            "last_disconnect": self.last_disconnect,
        }
