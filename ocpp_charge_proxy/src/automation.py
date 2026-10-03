"""Plug-in schedule and automatic re-plug.

- Schedule: switch Plugged In on or off at set times, on chosen days, as
  many times a day as you like. Times are local (the add-on's TZ, which Home
  Assistant sets to your configured time zone). A time missed while the
  add-on was stopped isn't caught up.
- Re-plug: if the car is plugged in but the provider hasn't started a
  session after `after_min` minutes, unplug, wait REPLUG_WAIT_S seconds and
  plug back in, up to `attempts` times. The count resets when a session
  starts or when the car is unplugged by anything else. If your supplier's
  smart charging plan is available (src/smart_charging.py), a planned slot
  counts as an answer: no re-plug while one is planned, only when nothing
  has been scheduled `after_min` minutes after plugging in.

- At start-up: if the schedule is on and the add-on starts inside a
  plugged-in stretch (the last schedule time before now was a plug-in) with
  Plugged In off, it plugs in, as if it had been running at that time.
- Ready time: optionally, when the schedule plugs in, set your supplier's
  smart charging ready-by time to the schedule's next unplug
  (src/ready_time.py). Only at a scheduled plug-in.

Settings are saved in /data/automation.json and set on the web page
(Settings tab for re-plug). Until they're saved, re-plug uses the defaults.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from src.ready_time import check_unplug_times

logger = logging.getLogger(__name__)

REPLUG_WAIT_S = 30
STARTUP_READY_S = 180  # keep trying to set the ready time this long after start-up
TICK_S = 15
CATCH_UP_S = 300  # a scheduled time is still run if noticed within this
ACTIONS = ("plug", "unplug")


@dataclass(frozen=True)
class ReplugOptions:
    """Re-plug settings from the add-on configuration."""

    enabled: bool = True
    after_min: int = 10
    attempts: int = 3

    def as_dict(self) -> dict:
        return {"enabled": self.enabled, "after_min": self.after_min, "attempts": self.attempts}


def _iso_local(dt: Optional[datetime.datetime]) -> Optional[str]:
    return dt.isoformat(timespec="seconds") if dt else None


def _iso_from_epoch(t: Optional[float]) -> Optional[str]:
    if t is None:
        return None
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_hhmm(value) -> tuple[int, int]:
    try:
        hh, mm = str(value).strip().split(":")
        h, m = int(hh), int(mm)
    except (ValueError, AttributeError):
        raise ValueError(f"Time must be HH:MM, got {value!r}") from None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(f"Time must be HH:MM, got {value!r}")
    return h, m


def validate_entry(raw: dict) -> dict:
    """A schedule entry: {id, time "HH:MM", days [0=Mon..6=Sun], action, enabled}."""
    if not isinstance(raw, dict):
        raise ValueError("Each entry must be an object")
    h, m = _parse_hhmm(raw.get("time"))
    action = raw.get("action")
    if action not in ACTIONS:
        raise ValueError(f"Action must be one of {ACTIONS}, got {action!r}")
    days = raw.get("days", list(range(7)))
    if not isinstance(days, list) or not days or any(
        not isinstance(d, int) or isinstance(d, bool) or not 0 <= d <= 6 for d in days
    ):
        raise ValueError("Days must be a non-empty list of 0 (Mon) to 6 (Sun)")
    return {
        "id": str(raw.get("id") or uuid.uuid4().hex[:8]),
        "time": f"{h:02d}:{m:02d}",
        "days": sorted(set(days)),
        "action": action,
        "enabled": bool(raw.get("enabled", True)),
    }


WEEK_MIN = 7 * 1440
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def plugged_segments(entries: list[dict]) -> list[tuple[int, int]]:
    """When the schedule has the car plugged in over a week, as (start, end)
    minutes from Monday 00:00 (the same as the web page's week view)."""
    events = []
    for e in entries:
        if not e.get("enabled", True):
            continue
        h, m = _parse_hhmm(e["time"])
        events += [(d * 1440 + h * 60 + m, e["action"] == "plug") for d in e["days"]]
    events.sort()
    segs: list[tuple[int, int]] = []
    if events:
        state, since = events[-1][1], 0  # carried over from the end of the week
        for t, plug in events:
            if plug != state:
                if state:
                    segs.append((since, t))
                state, since = plug, t
        if state:
            segs.append((since, WEEK_MIN))
    return segs


def longest_day(entries: list[dict]) -> Optional[tuple[int, int]]:
    """The most plugged-in minutes in any 24 hours, and when that starts."""
    segs = plugged_segments(entries)
    both = segs + [(a + WEEK_MIN, b + WEEK_MIN) for a, b in segs]
    worst = None
    for a, _ in segs:
        total = sum(max(0, min(y, a + 1440) - max(x, a)) for x, y in both)
        if worst is None or total > worst[0]:
            worst = (total, a)
    return worst


def check_daily_cap(entries: list[dict], cap_min: int, provider: str) -> None:
    """Octopus schedules at most 6 hours of smart charging a day: refuse a
    schedule that plugs in for longer in any 24 hours."""
    worst = longest_day(entries)
    if worst and worst[0] > cap_min:
        total, start = worst
        raise ValueError(
            f"{provider} schedules at most {cap_min // 60} hours of smart charging a day, but the schedule "
            f"plugs in for {total // 60}h {total % 60:02d}m in the 24 hours from "
            f"{DAYS[start // 1440 % 7]} {start % 1440 // 60:02d}:{start % 60:02d}: shorten it"
        )


def _local_now() -> datetime.datetime:
    return datetime.datetime.now().astimezone()


def timezone_name() -> str:
    return os.environ.get("TZ") or _local_now().tzname() or "UTC"


class Automation:
    def __init__(
        self,
        data_dir: Optional[str],
        options: ReplugOptions = ReplugOptions(),
        now: Callable[[], datetime.datetime] = _local_now,
        clock: Callable[[], float] = time.time,
        localize: Callable[[datetime.datetime], datetime.datetime] = lambda naive: naive.astimezone(),
    ) -> None:
        self._localize = localize  # naive local time -> aware (local DST rules)
        self._path = os.path.join(data_dir, "automation.json") if data_dir else None
        self._now = now
        self._clock = clock
        self._options = options
        self.schedule_enabled = False
        self.entries: list[dict] = []
        self.ready_time = False  # set the supplier's ready time at scheduled plug-ins
        self.ready_status: Optional[dict] = None  # the last time it was set (or why not)
        self.replug = options.as_dict()
        # Runtime (not saved)
        self.attempts_used = 0
        self.waiting_since: Optional[float] = None  # plugged in, no session, since
        self.replugging = False
        self.gave_up = False
        self.scheduled = False  # waiting, but your supplier has a slot planned
        self.last_replug: Optional[float] = None
        self.last_run: Optional[dict] = None  # last schedule entry run
        self._last_check: Optional[datetime.datetime] = None
        self._load()

    # --- persistence ---------------------------------------------------------

    def _load(self) -> None:
        if not self._path:
            return
        data = None
        for path in (self._path, self._path + ".bak"):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                break
            except FileNotFoundError:
                continue
            except Exception:
                logger.warning("Automation settings %s are unreadable", path)
        if not isinstance(data, dict):
            return
        schedule = data.get("schedule") or {}
        self.schedule_enabled = bool(schedule.get("enabled", False))
        self.ready_time = bool(schedule.get("ready_time", False))
        entries = []
        for raw in schedule.get("entries") or []:
            try:
                entries.append(validate_entry(raw))
            except ValueError:
                logger.warning("Ignoring invalid schedule entry %r", raw)
        self.entries = entries
        # Saved re-plug settings (set on the web page) win over the defaults
        replug = data.get("replug")
        if isinstance(replug, dict):
            try:
                self.replug = self._valid_replug({**self.replug, **replug})
            except ValueError:
                pass

    def _save(self) -> None:
        if not self._path:
            return
        try:
            tmp = self._path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({
                    "schedule": {"enabled": self.schedule_enabled, "entries": self.entries,
                                 "ready_time": self.ready_time},
                    "replug": self.replug,
                }, f, indent=1)
                f.flush()
                os.fsync(f.fileno())
            if os.path.exists(self._path):
                os.replace(self._path, self._path + ".bak")
            os.replace(tmp, self._path)
        except Exception:
            logger.warning("Could not save automation settings", exc_info=True)

    # --- settings ------------------------------------------------------------

    def set_schedule(self, enabled: Optional[bool] = None, entries: Optional[list] = None,
                     ready_time: Optional[bool] = None, ready_times: Optional[list] = None,
                     provider: str = "your supplier", daily_cap_min: Optional[int] = None) -> None:
        """ready_times: the times your supplier accepts as a ready time (None:
        unknown). While the schedule sets it, unplug times must be among them,
        and with daily_cap_min (Octopus: 360) it can't plug in for longer than
        that in any 24 hours. Checked when times are saved or the ready time
        is turned on, so the schedule can always be switched off."""
        new_entries = self.entries
        if entries is not None:
            if not isinstance(entries, list):
                raise ValueError("Entries must be a list")
            if len(entries) > 50:
                raise ValueError("At most 50 schedule entries")
            new_entries = [validate_entry(e) for e in entries]
        checking = entries is not None or bool(ready_time)
        if checking and (self.ready_time if ready_time is None else bool(ready_time)):
            if ready_times:
                check_unplug_times(new_entries, ready_times, provider)
            if daily_cap_min:
                check_daily_cap(new_entries, daily_cap_min, provider)
        self.entries = new_entries
        if enabled is not None:
            self.schedule_enabled = bool(enabled)
        if ready_time is not None:
            self.ready_time = bool(ready_time)
        self._save()
        logger.info(
            "Schedule %s, %d entr%s", "on" if self.schedule_enabled else "off",
            len(self.entries), "y" if len(self.entries) == 1 else "ies",
        )

    @staticmethod
    def _valid_replug(values: dict) -> dict:
        try:
            after = int(values["after_min"])
            attempts = int(values["attempts"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("after_min and attempts must be whole numbers") from None
        if not 1 <= after <= 240:
            raise ValueError("after_min must be 1 to 240 minutes")
        if not 0 <= attempts <= 20:
            raise ValueError("attempts must be 0 to 20")
        return {"enabled": bool(values.get("enabled", True)), "after_min": after, "attempts": attempts}

    def set_replug(self, **changes) -> None:
        allowed = {k: v for k, v in changes.items() if k in ("enabled", "after_min", "attempts") and v is not None}
        self.replug = self._valid_replug({**self.replug, **allowed})
        if not self.replug["enabled"]:
            self.waiting_since = None
        self.gave_up = self.gave_up and self.attempts_used >= self.replug["attempts"]
        self._save()
        logger.info(
            "Auto re-plug %s (after %d min, up to %d tries)",
            "on" if self.replug["enabled"] else "off",
            self.replug["after_min"], self.replug["attempts"],
        )

    # --- schedule ------------------------------------------------------------

    def _occurrences(self, entry: dict, start: datetime.date, days: int):
        h, m = _parse_hhmm(entry["time"])
        for i in range(days):
            day = start + datetime.timedelta(days=i)
            if day.weekday() in entry["days"]:
                yield self._localize(datetime.datetime(day.year, day.month, day.day, h, m))

    def due(self) -> list[dict]:
        """Entries whose time has come since the last check (empty on the first)."""
        now = self._now()
        prev, self._last_check = self._last_check, now
        if prev is None or not self.schedule_enabled or now <= prev:
            return []
        start = prev.date() - datetime.timedelta(days=1)
        span = (now.date() - start).days + 1
        due = []
        for entry in self.entries:
            if not entry["enabled"]:
                continue
            for occ in self._occurrences(entry, start, span):
                if prev < occ <= now and (now - occ).total_seconds() <= CATCH_UP_S:
                    due.append((occ, entry))
        due.sort(key=lambda x: x[0])
        return [e for _, e in due]

    def last_event(self, at: datetime.datetime) -> Optional[tuple[datetime.datetime, dict]]:
        """The schedule's most recent enabled time at or before `at` (within a week)."""
        best = None
        start = at.date() - datetime.timedelta(days=7)
        for entry in self.entries:
            if not entry["enabled"]:
                continue
            for occ in self._occurrences(entry, start, 9):
                # an unplug at the same minute as a plug wins (it's later in the list)
                if occ <= at and (best is None or occ > best[0] or
                                  (occ == best[0] and entry["action"] == "unplug")):
                    best = (occ, entry)
        return best

    def in_plug_window(self, at: Optional[datetime.datetime] = None) -> Optional[datetime.datetime]:
        """When the plugged-in stretch we're in started, if the schedule (on)
        has the car plugged in at `at` (default now); else None."""
        if not self.schedule_enabled:
            return None
        last = self.last_event(at or self._now())
        return last[0] if last and last[1]["action"] == "plug" else None

    def next_unplug(self, after: datetime.datetime) -> Optional[datetime.datetime]:
        """The schedule's next unplug after `after` (within a week)."""
        best = None
        for entry in self.entries:
            if not entry["enabled"] or entry["action"] != "unplug":
                continue
            for occ in self._occurrences(entry, after.date(), 8):
                if occ > after:
                    if best is None or occ < best:
                        best = occ
                    break
        return best

    def next_action(self) -> Optional[dict]:
        if not self.schedule_enabled:
            return None
        now = self._now()
        best = None
        for entry in self.entries:
            if not entry["enabled"]:
                continue
            for occ in self._occurrences(entry, now.date(), 8):
                if occ > now and (best is None or occ < best[0]):
                    best = (occ, entry)
                    break
        if best is None:
            return None
        return {"time": _iso_local(best[0]), "action": best[1]["action"], "entry_id": best[1]["id"]}

    # --- re-plug -------------------------------------------------------------

    def replug_due(self, plugged_in: bool, in_session: bool, connected: bool,
                   scheduled: Optional[bool] = None) -> bool:
        """Call regularly; True when it's time to re-plug.

        scheduled: your supplier has a charge slot planned (None: unknown, so
        only a session counts)."""
        now = self._clock()
        self.scheduled = bool(scheduled) and plugged_in and not in_session
        if self.replugging:
            return False
        if in_session or not plugged_in or scheduled:
            # A session started or was scheduled, or the car was unplugged:
            # start afresh (if a planned slot is dropped, the wait starts then)
            self.attempts_used = 0
            self.gave_up = False
            self.waiting_since = None
            return False
        if not connected or not self.replug["enabled"]:
            self.waiting_since = None  # the wait restarts once back online / on
            return False
        if self.waiting_since is None:
            self.waiting_since = now
            return False
        if now - self.waiting_since < self.replug["after_min"] * 60:
            return False
        if self.attempts_used >= self.replug["attempts"]:
            if not self.gave_up:
                self.gave_up = True
                logger.warning(
                    "Still no session %d min after plugging in, after %d re-plug(s): giving up "
                    "until the car is next unplugged or a session starts",
                    self.replug["after_min"], self.attempts_used,
                )
            return False
        return True

    async def run_replug(self, unplug: Callable[..., Awaitable[None]], plug: Callable[..., Awaitable[None]],
                         wait_s: float = REPLUG_WAIT_S) -> None:
        self.attempts_used += 1
        logger.warning(
            "No session from the provider %d min after plugging in: re-plugging (try %d of %d)",
            self.replug["after_min"], self.attempts_used, self.replug["attempts"],
        )
        self.replugging = True
        try:
            await unplug(source="auto re-plug")
            await asyncio.sleep(wait_s)
            await plug(source="auto re-plug")
        finally:
            self.replugging = False
            self.last_replug = self._clock()
            self.waiting_since = self._clock()

    # --- status --------------------------------------------------------------

    def replug_status(self) -> dict:
        r = self.replug
        if not r["enabled"]:
            status = "off"
        elif self.replugging:
            status = "replugging"
        elif self.gave_up:
            status = "gave_up"
        elif self.scheduled:
            status = "scheduled"
        elif self.waiting_since is not None:
            status = "waiting"
        else:
            status = "idle"
        next_at = None
        if status == "waiting" and self.attempts_used < r["attempts"]:
            next_at = self.waiting_since + r["after_min"] * 60
        return {
            **r,
            "status": status,
            "attempts_used": self.attempts_used,
            "waiting_since": _iso_from_epoch(self.waiting_since),
            "next_replug_at": _iso_from_epoch(next_at),
            "last_replug": _iso_from_epoch(self.last_replug),
        }

    def snapshot(self) -> dict:
        return {
            "timezone": timezone_name(),
            "now": _iso_local(self._now()),
            "schedule": {
                "enabled": self.schedule_enabled,
                "entries": self.entries,
                "next": self.next_action(),
                "last_run": self.last_run,
                "ready_time": self.ready_time,
                "ready_status": self.ready_status,
            },
            "replug": self.replug_status(),
        }

    def publish(self, shared_state) -> None:
        shared_state.schedule_enabled = self.schedule_enabled
        shared_state.schedule_next = self.next_action()
        shared_state.replug = self.replug_status()


async def apply_ready_time(automation: "Automation",
                           set_ready_time: Callable[[datetime.datetime], Awaitable[dict]],
                           log_errors: bool = True) -> dict:
    """At a scheduled plug-in: ready time = the schedule's next unplug."""
    now = automation._now()
    unplug = automation.next_unplug(now)
    if unplug is None:
        result = {"error": "There's no unplug in the schedule after this plug-in"}
    else:
        try:
            result = await set_ready_time(unplug)
        except Exception as err:
            result = {"unplug": unplug.isoformat(timespec="minutes"), "error": str(err)}
    if result.get("error") and log_errors:
        logger.warning("Ready time not set: %s", result["error"])
    automation.ready_status = {**result, "at": _iso_from_epoch(automation._clock())}
    return result


async def automation_loop(
    automation: Automation,
    shared_state,
    plug: Callable[[], Awaitable[None]],
    unplug: Callable[[], Awaitable[None]],
    tick_s: float = TICK_S,
    scheduled: Optional[Callable[[], Optional[bool]]] = None,
    set_ready_time: Optional[Callable[[datetime.datetime], Awaitable[dict]]] = None,
) -> None:
    """Run the schedule and re-plug for the life of the add-on.

    scheduled: whether your supplier has a charge slot planned (None if its
    integration isn't there); also shown as the add-on's status."""
    started = automation._clock()
    ready_pending = False  # a start-up plug-in's ready time, until HA is there to take it
    first = True
    while True:
        try:
            shared_state.scheduled = scheduled() if scheduled is not None else None
            if first:
                first = False
                since = automation.in_plug_window()
                if since is not None and not shared_state.plugged_in:
                    logger.info("Started inside a scheduled plug-in (since %s): plugging in", since.strftime("%a %H:%M"))
                    automation.last_run = {"entry_id": None, "action": "plug",
                                           "timestamp": _iso_from_epoch(automation._clock()), "startup": True}
                    await plug(source="schedule")
                    ready_pending = automation.ready_time and set_ready_time is not None
            if ready_pending:
                # HA (or the supplier's sensor) may not be there yet just after start-up
                last_try = automation._clock() - started >= STARTUP_READY_S
                result = await apply_ready_time(automation, set_ready_time, log_errors=last_try)
                ready_pending = bool(result.get("error")) and not last_try
            for entry in automation.due():
                logger.info("Schedule: %s at %s", "plugging in" if entry["action"] == "plug" else "unplugging", entry["time"])
                automation.last_run = {
                    "entry_id": entry["id"], "action": entry["action"],
                    "timestamp": _iso_from_epoch(automation._clock()),
                }
                await (plug if entry["action"] == "plug" else unplug)(source="schedule")
                if entry["action"] == "plug" and automation.ready_time and set_ready_time is not None:
                    await apply_ready_time(automation, set_ready_time)
            if automation.replug_due(
                # Plugged In and waiting (Preparing); not e.g. Unavailable
                plugged_in=bool(shared_state.plugged_in) and shared_state.state == "Preparing",
                in_session=shared_state.transaction_id is not None,
                connected=bool(shared_state.connected_to_server),
                scheduled=shared_state.scheduled,
            ):
                automation.publish(shared_state)
                await automation.run_replug(unplug, plug)
            automation.publish(shared_state)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Automation cycle failed", exc_info=True)
        await asyncio.sleep(tick_s)
