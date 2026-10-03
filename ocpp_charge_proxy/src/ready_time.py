"""Set your supplier's ready-by time from the plug-in schedule.

When the schedule plugs in (and the option is on, Automation tab), the
add-on sets the smart charging "target time" of your supplier's integration
to the schedule's next unplug, so the car is charged by the time it's
"unplugged". Done once per scheduled plug-in, never at other times.

Octopus Energy and EDF Energy (both Kraken) have a target time entity next
to their dispatching sensor:

- time.<prefix>_intelligent_target_time    (time.set_value)
- select.<prefix>_intelligent_target_time  (select.select_option, "HH:MM")

and only accept 04:00 to 11:00 in 30-minute steps (the select's options).
The add-on picks the latest of those at or before the unplug; if there's
none before it (e.g. plugged in 4pm to 10pm), nothing is set and the page
says why. E.ON Next's integration has no ready time setting.

Kept free of I/O; HaLink makes the calls.
"""

from __future__ import annotations

import datetime
from typing import Optional

DEFAULT_TIMES = [f"{h:02}:{m:02}" for h in range(4, 12) for m in (0, 30) if (h, m) <= (11, 0)]


def target_time_entity(states: list[dict], dispatch_entity: Optional[str]) -> Optional[dict]:
    """The target time entity belonging to the supplier's dispatching sensor."""
    if not dispatch_entity or not dispatch_entity.startswith("binary_sensor.") \
            or not dispatch_entity.endswith("_dispatching"):
        return None
    base = dispatch_entity[len("binary_sensor."):-len("dispatching")]  # e.g. octopus_energy_<id>_intelligent_
    by_id = {st.get("entity_id"): st for st in states or []}
    for domain in ("time", "select"):  # the time entity is the newer one
        st = by_id.get(f"{domain}.{base}target_time")
        if st and str(st.get("state")).lower() not in ("unavailable",):
            return st
    return None


def allowed_times(entity: Optional[dict]) -> list[str]:
    """"HH:MM" the entity accepts: a select's options, else 04:00-11:00."""
    options = ((entity or {}).get("attributes") or {}).get("options")
    if isinstance(options, list):
        valid = [o for o in options if isinstance(o, str) and len(o) == 5 and o[2] == ":"]
        if valid:
            return valid
    return list(DEFAULT_TIMES)


def pick_ready_time(now: datetime.datetime, unplug: datetime.datetime,
                    allowed: list[str]) -> Optional[datetime.datetime]:
    """The latest allowed time of day after `now` and at or before `unplug`."""
    best = None
    day = now.date()
    while day <= unplug.date():
        for hhmm in allowed:
            h, m = int(hhmm[:2]), int(hhmm[3:])
            t = datetime.datetime(day.year, day.month, day.day, h, m, tzinfo=unplug.tzinfo)
            if now < t <= unplug and (best is None or t > best):
                best = t
        day += datetime.timedelta(days=1)
    return best


def service_call(entity: dict, ready: datetime.datetime) -> dict:
    """The HA call_service message that sets the entity to `ready`."""
    entity_id = entity["entity_id"]
    if entity_id.startswith("select."):
        return {"type": "call_service", "domain": "select", "service": "select_option",
                "target": {"entity_id": entity_id}, "service_data": {"option": ready.strftime("%H:%M")}}
    return {"type": "call_service", "domain": "time", "service": "set_value",
            "target": {"entity_id": entity_id}, "service_data": {"time": ready.strftime("%H:%M:00")}}
