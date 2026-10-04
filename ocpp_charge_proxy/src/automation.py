"""Plug-in schedule and automatic re-plug.

- Schedule: switch Plugged In on or off at set times, on chosen days, as
  many times a day as you like. Times are local (the add-on's TZ, which Home
  Assistant sets to your configured time zone). A time missed while the
  add-on was stopped isn't caught up.
- Re-plug: if the car is plugged in but the provider hasn't started a
  session after `after_min` minutes, unplug, wait REPLUG_WAIT_S seconds and
  plug back in, up to `attempts` times. The count resets when a session
  starts or when the car is unplugged by anything else. If your supplier's
  smart charging plan is available (src/smart_charging.py), a slot planned
  for later counts as an answer: no re-plug while one is planned, only when
  nothing has been scheduled `after_min` minutes after plugging in. A slot
  running now doesn't: the supplier should be charging. But it may only
  start a session at the next half hour (Octopus does, e.g. after the
  add-on restarted mid-slot), so the wait is counted from then: with no
  session `after_min` minutes after the next :00 or :30, it re-plugs.

- One-off times: an entry with a `date` runs once, on that day, and is
  removed after it has run. Skips: any upcoming slot (a plug-in and its
  unplug, weekly or one-off) can be skipped once; skipped times don't
  run, and the skips are forgotten a day after.
- Auto plug-in charge: when auto plug-in (low SoC) switches Plugged In on
  and its "set my supplier's ready time" option is on, plan_auto_plug adds
  a one-off slot to the schedule: plug in now, unplug at the first ready
  time your supplier accepts at least the chosen hours away. If that puts
  more than Octopus's 6 hours in 24 (only checked with Force schedule on
  supplier on, as for the schedule), the next scheduled slot starts that
  much later (its first hours move to now). If it then meets or overlaps
  the next scheduled slot, the two become one slot. The ready time is set
  for the end of the slot. Its entries carry "source": "auto_plug" and run
  even with the schedule off.
- At start-up: if the schedule is on and the add-on starts inside a
  plugged-in stretch (the last schedule time before now was a plug-in) with
  Plugged In off, it plugs in, as if it had been running at that time.
- Graceful unplug: with the ready time on (Force schedule on supplier), a
  scheduled unplug during a session waits up to `unplug_wait_s` (default
  GRACEFUL_UNPLUG_S, set on the page; 0 = don't wait) for the supplier to
  stop the session itself (RemoteStop), then unplugs.
- Plan check: with the ready time on, while the schedule has the car
  plugged in, the supplier's planned slots up to the ready time are checked
  against the schedule (src/plan_check.py); a mismatch is shown on the page.
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

from src.plan_check import SETTLE_S, check_plan
from src.ready_time import ALL_DAY_TIMES, check_unplug_times

logger = logging.getLogger(__name__)

REPLUG_WAIT_S = 30
HALF_HOUR_S = 1800
STARTUP_READY_S = 180  # keep trying to set the ready time this long after start-up
GRACEFUL_UNPLUG_S = 60  # with Force schedule on supplier: wait this long for it to stop a session (default)
MAX_UNPLUG_WAIT_S = 600
PENDING_TICK_S = 2  # check this often while waiting
TICK_S = 15
CATCH_UP_S = 300  # a scheduled time is still run if noticed within this
ACTIONS = ("plug", "unplug")
AUTO_SOURCE = "auto_plug"  # entries added by an auto plug-in charge
CHARGE_NOW_SOURCE = "charge_now"  # ... or by the Charge now button
AUTO_SOURCES = (AUTO_SOURCE, CHARGE_NOW_SOURCE)
ONE_OFF_KEEP = datetime.timedelta(days=14)  # one-off times (and skips) are kept this long after they ran


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


def _parse_iso(value) -> Optional[datetime.datetime]:
    if not value:
        return None
    try:
        dt = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.astimezone()


def _parse_date(value) -> datetime.date:
    try:
        return datetime.date.fromisoformat(str(value))
    except ValueError:
        raise ValueError(f"Date must be YYYY-MM-DD, got {value!r}") from None


def validate_entry(raw: dict) -> dict:
    """A schedule entry: {id, time "HH:MM", days [0=Mon..6=Sun], action, enabled},
    or a one-off: the same with "date": "YYYY-MM-DD" (days is then that day)."""
    if not isinstance(raw, dict):
        raise ValueError("Each entry must be an object")
    h, m = _parse_hhmm(raw.get("time"))
    action = raw.get("action")
    if action not in ACTIONS:
        raise ValueError(f"Action must be one of {ACTIONS}, got {action!r}")
    if raw.get("date"):
        date = _parse_date(raw["date"])
        out = {
            "id": str(raw.get("id") or uuid.uuid4().hex[:8]),
            "time": f"{h:02d}:{m:02d}",
            "days": [date.weekday()],
            "date": date.isoformat(),
            "action": action,
            "enabled": bool(raw.get("enabled", True)),
        }
        if raw.get("source") in AUTO_SOURCES:
            out["source"] = raw["source"]
        return out
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


DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def plugged_windows(events):
    """(time, is_plug) events in time order -> the stretches plugged in, as
    (start, end). A stretch still open at the last event is left out."""
    windows = []
    state, since = None, None
    for t, plug in events:
        if plug and state is not True:
            state, since = True, t
        elif not plug:
            if state is True:
                windows.append((since, t))
            state = False
    return windows


def longest_day(windows, after, until):
    """The most plugged-in minutes in any 24 hours starting at a stretch's
    start between `after` and `until`: (minutes, start), or None."""
    worst = None
    for a, _ in windows:
        if not after <= a <= until:
            continue
        end = a + datetime.timedelta(days=1)
        total = sum(max(0.0, (min(y, end) - max(x, a)).total_seconds()) for x, y in windows) / 60
        if worst is None or total > worst[0]:
            worst = (int(round(total)), a)
    return worst


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
        self.skips: list[dict] = []  # [{"entry_id", "date"}]: times skipped once
        self.ready_time = False  # set the supplier's ready time at scheduled plug-ins
        self.ready_status: Optional[dict] = None  # the last time it was set (or why not)
        self.auto_plug_last: Optional[dict] = None  # the last auto plug-in charge planned
        self.unplug_wait_s = GRACEFUL_UNPLUG_S
        self.plan_check: Optional[dict] = None  # the supplier's plan vs the schedule, while plugged in
        self._plan_problems: tuple = ()
        self.replug = options.as_dict()
        # Runtime (not saved)
        self.attempts_used = 0
        self.waiting_since: Optional[float] = None  # plugged in, no session, since
        self.replugging = False
        self.gave_up = False
        self.scheduled = False  # waiting, but your supplier has a slot planned
        self.slot_now = False  # waiting, though your supplier's slot is running
        self.last_replug: Optional[float] = None
        self.last_run: Optional[dict] = None  # last schedule entry run
        self.unplug_at: Optional[float] = None  # a scheduled unplug waiting for the supplier, until
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
        try:
            self.unplug_wait_s = self._valid_wait(schedule.get("unplug_wait_s", GRACEFUL_UNPLUG_S))
        except ValueError:
            pass
        entries = []
        for raw in schedule.get("entries") or []:
            try:
                entries.append(validate_entry(raw))
            except ValueError:
                logger.warning("Ignoring invalid schedule entry %r", raw)
        self.entries = entries
        self.skips = [k for k in schedule.get("skips") or []
                      if isinstance(k, dict) and k.get("entry_id") and k.get("date")]
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
                                 "ready_time": self.ready_time, "skips": self.skips,
                                 "unplug_wait_s": self.unplug_wait_s},
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
                     provider: str = "your supplier", daily_cap_min: Optional[int] = None,
                     unplug_wait_s=None) -> None:
        """ready_times: the times your supplier accepts as a ready time (None:
        unknown). While the schedule sets it, unplug times must be among them,
        and with daily_cap_min (Octopus: 360) it can't plug in for longer than
        that in any 24 hours. Checked when times are saved or the ready time
        is turned on, so the schedule can always be switched off."""
        wait = None if unplug_wait_s is None else self._valid_wait(unplug_wait_s)
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
                check_unplug_times([e for e in new_entries if not self._past_one_off(e)], ready_times, provider)
            if daily_cap_min:
                self.check_daily_cap(new_entries, daily_cap_min, provider)
        self.entries = new_entries
        ids = {e["id"] for e in self.entries}
        self.skips = [k for k in self.skips if k["entry_id"] in ids]
        self._prune()
        if enabled is not None:
            self.schedule_enabled = bool(enabled)
        if ready_time is not None:
            self.ready_time = bool(ready_time)
        if wait is not None:
            self.unplug_wait_s = wait
        self._save()
        logger.info(
            "Schedule %s, %d entr%s", "on" if self.schedule_enabled else "off",
            len(self.entries), "y" if len(self.entries) == 1 else "ies",
        )

    @staticmethod
    def _valid_wait(value) -> int:
        try:
            wait = int(value)
        except (TypeError, ValueError):
            raise ValueError("The unplug wait must be a whole number of seconds") from None
        if not 0 <= wait <= MAX_UNPLUG_WAIT_S:
            raise ValueError(f"The unplug wait must be 0 to {MAX_UNPLUG_WAIT_S} seconds")
        return wait

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
        once = entry.get("date")
        for i in range(days):
            day = start + datetime.timedelta(days=i)
            if (day.isoformat() == once) if once else (day.weekday() in entry["days"]):
                yield self._localize(datetime.datetime(day.year, day.month, day.day, h, m))

    def timeline(self, start: datetime.date, days: int, entries: Optional[list] = None,
                 skips: Optional[list] = None) -> list:
        """Every enabled time from `start` for `days` days: (when, entry, skipped), in order."""
        skips = self.skips if skips is None else skips
        out = []
        for entry in self._active_entries() if entries is None else entries:
            if not entry["enabled"]:
                continue
            for occ in self._occurrences(entry, start, days):
                out.append((occ, entry, {"entry_id": entry["id"], "date": occ.date().isoformat()} in skips))
        # an unplug at the same minute as a plug comes after it
        out.sort(key=lambda x: (x[0], x[1]["action"] == "unplug"))
        return out

    def _active_entries(self) -> list:
        """The entries that run: all of them with the schedule on, else only
        those an auto plug-in charge added."""
        if self.schedule_enabled:
            return self.entries
        return [e for e in self.entries if e.get("source") in AUTO_SOURCES]

    def windows(self, entries: Optional[list] = None, now: Optional[datetime.datetime] = None,
                skips: Optional[list] = None) -> list:
        """The stretches the schedule has the car plugged in, a week back to 8 days on."""
        now = now or self._now()
        tl = self.timeline(now.date() - datetime.timedelta(days=7), 16, entries, skips)
        return plugged_windows([(t, e["action"] == "plug") for t, e, skipped in tl if not skipped])

    def _longest_day(self, entries: list, skips: Optional[list] = None):
        now = self._now()
        return longest_day(self.windows(entries, now, skips), now - datetime.timedelta(days=1),
                           now + datetime.timedelta(days=7))

    def check_daily_cap(self, entries: list, cap_min: int, provider: str, skips: Optional[list] = None) -> None:
        """Octopus schedules at most 6 hours of smart charging a day: refuse a
        schedule that plugs in for longer in any 24 hours over the coming week."""
        worst = self._longest_day(entries, skips)
        if worst and worst[0] > cap_min:
            total, start = worst
            raise ValueError(
                f"{provider} schedules at most {cap_min // 60} hours of smart charging a day, but the schedule "
                f"plugs in for {total // 60}h {total % 60:02d}m in the 24 hours from "
                f"{start.strftime('%a %H:%M')}: shorten it"
            )

    def _prune(self) -> bool:
        """Forget one-off times that have run and skips more than a day old."""
        now = self._now()
        keep = []
        for e in self.entries:
            if e.get("date"):
                h, m = _parse_hhmm(e["time"])
                d = _parse_date(e["date"])
                when = self._localize(datetime.datetime(d.year, d.month, d.day, h, m))
                if when < now - ONE_OFF_KEEP:  # kept a day, so its stretch stays known
                    continue
            keep.append(e)
        # (a skip is kept for a day after, e.g. last night's plug-in until it's over)
        skips = [k for k in self.skips if k["date"] >= (now.date() - ONE_OFF_KEEP).isoformat()]
        changed = len(keep) != len(self.entries) or len(skips) != len(self.skips)
        self.entries, self.skips = keep, skips
        return changed

    def _past_one_off(self, entry: dict) -> bool:
        """A one-off time that has already run (kept for the Sessions tab)."""
        if not entry.get("date"):
            return False
        h, m = _parse_hhmm(entry["time"])
        d = _parse_date(entry["date"])
        return self._localize(datetime.datetime(d.year, d.month, d.day, h, m)) < self._now()

    def one_off_runs(self) -> list:
        """The plugged-in stretches of the last 14 days that a one-off time
        started or ended, newest first: [{"start", "end", "source"}] ("auto_plug"
        if an auto plug-in charge added it, else "one_off")."""
        now = self._now()
        days = ONE_OFF_KEEP.days + 1
        out = []
        for s in self._stretches(now.date() - datetime.timedelta(days=days - 1), days, self._active_entries(), self.skips):
            ones = [e for e in (s["plug"], s["unplug"]) if e.get("date")]
            if ones and s["start"] <= now:
                source = next((e["source"] for e in ones if e.get("source") in AUTO_SOURCES), "one_off")
                out.append({"start": _iso_local(s["start"]), "end": _iso_local(s["end"]), "source": source})
        return out[::-1]

    def _stretches(self, start: datetime.date, days: int, entries: list, skips: list) -> list:
        """Plugged-in stretches with the entries that make them:
        [{"start", "plug", "end", "unplug"}] (a stretch still open at the end is left out)."""
        out, state, cur = [], None, None
        for t, e, skipped in self.timeline(start, days, entries, skips):
            if skipped:
                continue
            if e["action"] == "plug" and state is not True:
                state, cur = True, {"start": t, "plug": e}
            elif e["action"] == "unplug":
                if state is True:
                    cur.update(end=t, unplug=e)
                    out.append(cur)
                state = False
        return out

    def first_ready_at(self, target: datetime.datetime, ready_times: Optional[list] = None):
        """The first ready time your supplier accepts at or after `target`."""
        best = None
        for d in range(3):
            day = target.date() + datetime.timedelta(days=d)
            for t in ready_times or ALL_DAY_TIMES:
                h, m = _parse_hhmm(t)
                dt = self._localize(datetime.datetime(day.year, day.month, day.day, h, m))
                if dt >= target and (best is None or dt < best):
                    best = dt
        return best

    def last_ready_by(self, limit: datetime.datetime, ready_times: Optional[list] = None):
        """The last ready time your supplier accepts at or before `limit` (that day or the one before)."""
        best = None
        for d in (0, -1):
            day = limit.date() + datetime.timedelta(days=d)
            for t in ready_times or ALL_DAY_TIMES:
                h, m = _parse_hhmm(t)
                dt = self._localize(datetime.datetime(day.year, day.month, day.day, h, m))
                if dt <= limit and (best is None or dt > best):
                    best = dt
        return best

    def plan_auto_plug(self, minutes: int, ready_times: Optional[list] = None,
                       cap_min: Optional[int] = None, provider: str = "your supplier",
                       source: str = AUTO_SOURCE) -> dict:
        """An auto plug-in just plugged in: add a charge of `minutes` to the
        schedule as a one-off (see the module docstring). Returns what was done."""
        now = self._now().replace(second=0, microsecond=0)
        shortened = None
        if cap_min and minutes > cap_min:
            # Octopus schedules at most 6 hours a day: the charge can't be longer
            shortened = f"shortened to {cap_min // 60} hours, {provider}'s daily limit"
            minutes = cap_min
        end = self.first_ready_at(now + datetime.timedelta(minutes=minutes), ready_times)
        if end is None:
            raise ValueError("No ready time your supplier accepts in the next 2 days")
        if cap_min and end > now + datetime.timedelta(minutes=cap_min):
            # rounding up to a ready time would go over: the last one within the limit
            earlier = self.last_ready_by(now + datetime.timedelta(minutes=cap_min), ready_times)
            if earlier is not None and earlier > now:
                end = earlier

        def one_off(t, action):
            return validate_entry({"time": t.strftime("%H:%M"), "date": t.date().isoformat(),
                                   "action": action, "source": source})

        active = self._active_entries()
        skips = list(self.skips)
        plug, unplug = one_off(now, "plug"), one_off(end, "unplug")
        added = [plug]
        notes = [shortened] if shortened else []
        start_day = now.date() - datetime.timedelta(days=1)
        nxt = next((s for s in self._stretches(start_day, 9, active, skips) if s["end"] > now), None)
        moved = None
        if cap_min and nxt is not None and nxt["start"] > now:
            trial = self.windows(active + [plug, unplug], now, skips)
            worst = longest_day(trial, now - datetime.timedelta(days=1), now + datetime.timedelta(days=1))
            if worst and worst[0] > cap_min:
                # Over the daily cap: the next slot's first hours move to now
                shift = end - now
                new_start = nxt["start"] + shift
                skips.append({"entry_id": nxt["plug"]["id"], "date": nxt["start"].date().isoformat()})
                if new_start < nxt["end"]:
                    later = one_off(new_start, "plug")
                    added.append(later)
                    nxt = dict(nxt, start=new_start, plug=later)
                    notes.append(f"the {nxt['end'].strftime('%H:%M')} slot now starts at {new_start.strftime('%H:%M')}")
                else:
                    skips.append({"entry_id": nxt["unplug"]["id"], "date": nxt["end"].date().isoformat()})
                    notes.append("the next scheduled slot is skipped")
                    nxt = None
                moved = notes[-1]
        combined = nxt is not None and end >= nxt["start"]
        if combined:
            # One slot: plugged in from now to the scheduled unplug
            if nxt["start"] > now:
                if nxt["plug"] in added:
                    added.remove(nxt["plug"])
                else:
                    skips.append({"entry_id": nxt["plug"]["id"], "date": nxt["start"].date().isoformat()})
            slot_end = nxt["end"]
            notes.append(f"joined with the scheduled slot until {slot_end.strftime('%H:%M')}")
        else:
            added.append(unplug)
            slot_end = end
        self.entries = self.entries + added
        self.skips = [dict(k) for i, k in enumerate(skips) if k not in skips[:i]]
        self._save()
        self.auto_plug_last = {
            "at": _iso_local(now), "minutes": minutes, "ready_for": _iso_local(end),
            "end": _iso_local(slot_end), "combined": combined, "moved": moved, "notes": notes,
            "source": source,
        }
        logger.info("%s: plugged in until %s%s", "Charge now" if source == CHARGE_NOW_SOURCE else "Auto plug-in charge",
                    slot_end.strftime("%a %H:%M"),
                    f" ({'; '.join(notes)})" if notes else "")
        if cap_min:
            worst = longest_day(self.windows(now=now), now - datetime.timedelta(days=1),
                                now + datetime.timedelta(days=1))
            if worst and worst[0] > cap_min:
                logger.warning("Auto plug-in charge: the schedule now plugs in for %dh %02dm in 24 hours, "
                               "over %s's %d hours", worst[0] // 60, worst[0] % 60, provider, cap_min // 60)
        return self.auto_plug_last

    def set_skip(self, entry_id: str, date: str, skip: bool = True) -> None:
        """Skip (or un-skip) one upcoming time: entry `entry_id` on `date`."""
        self.set_skips([{"entry_id": entry_id, "date": date}], skip)

    def set_skips(self, times: list, skip: bool = True, daily_cap_min: Optional[int] = None,
                  provider: str = "your supplier") -> None:
        """Skip (or un-skip) several times at once, e.g. a slot's plug-in and
        unplug: [{"entry_id", "date"}, ...]. All or nothing. With daily_cap_min
        (Octopus, while the schedule sets its ready time), a change that takes a
        day over it is refused, as when saving the schedule."""
        if not isinstance(times, list) or not times:
            raise ValueError("Say which times to skip")
        keys = []
        for t in times:
            entry_id, date = str((t or {}).get("entry_id") or ""), (t or {}).get("date")
            entry = next((e for e in self.entries if e["id"] == entry_id), None)
            if entry is None:
                raise ValueError("No such schedule time (save the schedule first)")
            day = _parse_date(date)
            if not any(True for _ in self._occurrences(entry, day, 1)):
                raise ValueError(f"That time doesn't run on {date}")
            keys.append(({"entry_id": entry_id, "date": day.isoformat()}, entry))
        if daily_cap_min and self.ready_time:
            new = list(self.skips)
            for key, _ in keys:
                new = [k for k in new if k != key] + ([key] if skip else [])
            before, after = self._longest_day(self.entries), self._longest_day(self.entries, new)
            if after and after[0] > daily_cap_min and (not before or after[0] > before[0]):
                self.check_daily_cap(self.entries, daily_cap_min, provider, new)  # raises, with the details
        for key, entry in keys:
            self.skips = [k for k in self.skips if k != key] + ([key] if skip else [])
            logger.info("Schedule: %s the %s at %s on %s", "skipping" if skip else "no longer skipping",
                        "plug-in" if entry["action"] == "plug" else "unplug", entry["time"], key["date"])
        self._prune()
        self._save()

    def upcoming(self, days: int = 7) -> list:
        """The next times over `days` days, for the page."""
        now = self._now()
        out = []
        for occ, entry, skipped in self.timeline(now.date(), days + 1):
            if now < occ <= now + datetime.timedelta(days=days):
                out.append({"time": _iso_local(occ), "date": occ.date().isoformat(), "entry_id": entry["id"],
                            "action": entry["action"], "skipped": skipped, "one_off": bool(entry.get("date"))})
        return out[:30]

    def due(self) -> list[dict]:
        """Entries whose time has come since the last check (empty on the first)."""
        now = self._now()
        prev, self._last_check = self._last_check, now
        if prev is None or now <= prev:
            return []  # (with the schedule off, only auto plug-in times run: see timeline)
        start = prev.date() - datetime.timedelta(days=1)
        span = (now.date() - start).days + 1
        due = []
        for occ, entry, skipped in self.timeline(start, span):
            if prev < occ <= now and (now - occ).total_seconds() <= CATCH_UP_S:
                if skipped:
                    logger.info("Schedule: %s at %s skipped",
                                "plug-in" if entry["action"] == "plug" else "unplug", entry["time"])
                else:
                    due.append(entry)
        if prev.date() != now.date() and self._prune():  # tidy up once a day
            self._save()
        return due

    def last_event(self, at: datetime.datetime) -> Optional[tuple[datetime.datetime, dict]]:
        """The schedule's most recent enabled time at or before `at` (within a week)."""
        best = None
        for occ, entry, skipped in self.timeline(at.date() - datetime.timedelta(days=7), 9):
            if occ <= at and not skipped:
                best = (occ, entry)  # in order, so the last one wins
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
        for occ, entry, skipped in self.timeline(after.date(), 8):
            if occ > after and entry["action"] == "unplug" and not skipped:
                return occ
        return None

    def next_action(self) -> Optional[dict]:
        if not self.schedule_enabled:
            return None
        now = self._now()
        for occ, entry, skipped in self.timeline(now.date(), 8):
            if occ > now and not skipped:
                return {"time": _iso_local(occ), "action": entry["action"], "entry_id": entry["id"]}
        return None

    # --- the supplier's plan vs the schedule ------------------------------------

    def update_plan_check(self, plan: Optional[dict], plugged_in: bool) -> Optional[dict]:
        """plan: {"found", "provider", "slots", "supplier_ready"} from HaLink.supplier_plan.
        Checked only with Force schedule on supplier, while the schedule has the
        car plugged in, up to the ready time set for this stretch."""
        result = None
        since = self.in_plug_window() if self.ready_time and plugged_in else None
        end = self.next_unplug(self._now()) if since is not None else None
        if end is not None and plan and plan.get("found"):
            r = self.ready_status or {}
            ready_at = _parse_iso(r.get("ready_at"))
            set_at = _parse_iso(r.get("at"))
            # The ready time set for this stretch (at its plug-in)
            this_stretch = (not r.get("error") and set_at is not None and set_at >= since - datetime.timedelta(minutes=1))
            until = ready_at if this_stretch and ready_at is not None and since < ready_at <= end else end
            settle_from = max(since, set_at) if this_stretch else since
            check_at = settle_from + datetime.timedelta(seconds=SETTLE_S)
            if self._now() < check_at:
                result = {"status": "waiting", "start": _iso_local(since), "end": _iso_local(end),
                          "until": _iso_local(until), "check_at": _iso_local(check_at), "problems": []}
            else:
                result = check_plan(plan.get("slots") or [], since, end, until,
                                    ready_set=r.get("ready") if this_stretch else None,
                                    supplier_ready=plan.get("supplier_ready"),
                                    provider=plan.get("provider") or "Your supplier")
            result["provider"] = plan.get("provider")
        problems = tuple(result["problems"]) if result else ()
        if problems != self._plan_problems:
            for text in problems:
                if text not in self._plan_problems:
                    logger.warning("Supplier plan doesn't match the schedule: %s", text)
            if not problems and result and result["status"] != "waiting":
                logger.info("Supplier plan matches the schedule again")
            self._plan_problems = problems
        self.plan_check = result
        return result

    # --- re-plug -------------------------------------------------------------

    def replug_due(self, plugged_in: bool, in_session: bool, connected: bool,
                   scheduled: Optional[bool] = None, slot_now: Optional[bool] = None) -> bool:
        """Call regularly; True when it's time to re-plug.

        scheduled: your supplier has a charge slot planned (None: unknown, so
        only a session counts). slot_now: one is running now, so the wait
        counts from the next half hour (when the supplier may start)."""
        now = self._clock()
        self.scheduled = bool(scheduled) and plugged_in and not in_session
        self.slot_now = bool(slot_now) and plugged_in and not in_session
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
        if now < self._replug_at():
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

    def _replug_at(self) -> float:
        """When the wait for a session runs out (waiting_since must be set)."""
        start = self.waiting_since
        if self.slot_now:  # the supplier may only start at the next half hour
            start = -(-start // HALF_HOUR_S) * HALF_HOUR_S
        return start + self.replug["after_min"] * 60

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
            next_at = self._replug_at()
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
                "auto_plug_last": self.auto_plug_last,
                "one_off_runs": self.one_off_runs(),
                "unplug_wait_s": self.unplug_wait_s,
                "plan_check": self.plan_check,
                "skips": self.skips,
                "upcoming": self.upcoming(),
            },
            "replug": self.replug_status(),
        }

    def publish(self, shared_state) -> None:
        shared_state.schedule_enabled = self.schedule_enabled
        shared_state.schedule_next = self.next_action()
        shared_state.replug = self.replug_status()
        shared_state.unplug_pending = _iso_from_epoch(self.unplug_at)
        shared_state.plan_check = self.plan_check


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


async def auto_plug_charge(automation: "Automation", hours: float,
                           set_ready_time: Optional[Callable[[datetime.datetime], Awaitable[dict]]] = None,
                           ready_times: Optional[list] = None, cap_min: Optional[int] = None,
                           provider: str = "your supplier", source: str = AUTO_SOURCE) -> dict:
    """Auto plug-in (or Charge now) just plugged in: plan the charge and set the ready time."""
    plan = automation.plan_auto_plug(int(round(hours * 60)), ready_times, cap_min, provider, source)
    if set_ready_time is not None:
        await apply_ready_time(automation, set_ready_time)
    return plan


async def automation_loop(
    automation: Automation,
    shared_state,
    plug: Callable[[], Awaitable[None]],
    unplug: Callable[[], Awaitable[None]],
    tick_s: float = TICK_S,
    scheduled: Optional[Callable[[], Optional[bool]]] = None,
    slot_now: Optional[Callable[[], Optional[bool]]] = None,
    set_ready_time: Optional[Callable[[datetime.datetime], Awaitable[dict]]] = None,
    supplier_plan: Optional[Callable[[], Optional[dict]]] = None,
) -> None:
    """Run the schedule and re-plug for the life of the add-on.

    scheduled: whether your supplier has a charge slot planned for later,
    slot_now: whether one is running now (None if its integration isn't
    there); both also shown as the add-on's status.
    supplier_plan: the supplier's slots and ready time, for the plan check."""
    started = automation._clock()
    ready_pending = False  # a start-up plug-in's ready time, until HA is there to take it
    first = True
    while True:
        try:
            shared_state.scheduled = scheduled() if scheduled is not None else None
            shared_state.slot_now = slot_now() if slot_now is not None else None
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
                automation.last_run = {
                    "entry_id": entry["id"], "action": entry["action"],
                    "timestamp": _iso_from_epoch(automation._clock()),
                }
                if entry["action"] == "plug":
                    automation.unplug_at = None  # a waiting unplug is overtaken
                    logger.info("Schedule: plugging in at %s", entry["time"])
                    await plug(source="schedule")
                    if automation.ready_time and set_ready_time is not None:
                        await apply_ready_time(automation, set_ready_time)
                elif ((automation.ready_time or entry.get("source") in AUTO_SOURCES)
                      and automation.unplug_wait_s and shared_state.transaction_id is not None):
                    # Give the supplier a chance to end the session itself
                    automation.unplug_at = automation._clock() + automation.unplug_wait_s
                    logger.info("Schedule: unplug at %s, waiting up to %d s for the supplier to stop the session",
                                entry["time"], automation.unplug_wait_s)
                else:
                    logger.info("Schedule: unplugging at %s", entry["time"])
                    await unplug(source="schedule")
            if automation.unplug_at is not None:
                if not shared_state.plugged_in:
                    automation.unplug_at = None  # unplugged meanwhile
                elif shared_state.transaction_id is None:
                    logger.info("Schedule: the supplier stopped the session, unplugging")
                    automation.unplug_at = None
                    await unplug(source="schedule")
                elif automation._clock() >= automation.unplug_at:
                    logger.info("Schedule: the supplier didn't stop the session within %d s, unplugging",
                                automation.unplug_wait_s)
                    automation.unplug_at = None
                    await unplug(source="schedule")
            automation.update_plan_check(supplier_plan() if supplier_plan is not None else None,
                                         plugged_in=bool(shared_state.plugged_in))
            if automation.replug_due(
                # Plugged In and waiting (Preparing); not e.g. Unavailable
                plugged_in=bool(shared_state.plugged_in) and shared_state.state == "Preparing",
                in_session=shared_state.transaction_id is not None,
                connected=bool(shared_state.connected_to_server),
                # a slot running now with no session isn't an answer: re-plug
                scheduled=shared_state.scheduled and not shared_state.slot_now,
                slot_now=shared_state.slot_now,
            ):
                automation.publish(shared_state)
                await automation.run_replug(unplug, plug)
            automation.publish(shared_state)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Automation cycle failed", exc_info=True)
        await asyncio.sleep(min(tick_s, PENDING_TICK_S) if automation.unplug_at is not None else tick_s)
