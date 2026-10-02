"""Reads your Home Assistant sensors directly and acts on them.

Set up on the web page's Simulation tab (saved in /data/sensors.json):

- power_entity:  real power (W or kW) reported instead of the simulation
- soc_entity:    the car's SoC, reported to the provider (and car full / taper)
- plug_entity:   a car-connected binary sensor: off -> on switches Plugged In on
- auto_plug:     switch Plugged In on when the watched SoC drops below
                 auto_plug_soc; it watches auto_plug_entity if set, else
                 soc_entity (the monitor sensor is never reported)

The add-on talks to HA's websocket API through the Supervisor
(homeassistant_api: true gives it SUPERVISOR_TOKEN) and follows just these
entities with subscribe_entities, so changes arrive at once.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Awaitable, Callable, Optional

from src.autoplug import DEFAULT_AUTO_PLUG_SOC, AutoPlug, CarConnected

logger = logging.getLogger(__name__)

SUPERVISOR_WS = "ws://supervisor/core/websocket"
SUPERVISOR_API = "http://supervisor/core/api"
RECONNECT_DELAYS = (2, 5, 10, 20, 30, 60)
ENTITY_LIST_TTL_S = 30
_UNKNOWN_STATES = ("unavailable", "unknown", "none", "")
SETTING_KEYS = ("power_entity", "soc_entity", "plug_entity", "auto_plug", "auto_plug_entity", "auto_plug_soc")


def validate_settings(raw: dict, current: Optional[dict] = None) -> dict:
    """Merge `raw` into `current` and check it. Empty entity = not used."""
    if not isinstance(raw, dict):
        raise ValueError("Send a JSON object")
    out = dict(current or default_settings())
    for key in ("power_entity", "soc_entity", "plug_entity", "auto_plug_entity"):
        if key in raw:
            value = (raw[key] or "").strip() if isinstance(raw[key], (str, type(None))) else None
            if value is None:
                raise ValueError(f"{key} must be an entity ID or empty")
            domain = "binary_sensor" if key == "plug_entity" else "sensor"
            if value and not value.startswith(domain + "."):
                raise ValueError(f"{key} must be a {domain} entity")
            out[key] = value
    if "auto_plug" in raw:
        out["auto_plug"] = bool(raw["auto_plug"])
    if "auto_plug_soc" in raw:
        try:
            soc = int(float(raw["auto_plug_soc"]))
        except (TypeError, ValueError):
            raise ValueError("auto_plug_soc must be a number") from None
        if not 1 <= soc <= 99:
            raise ValueError("auto_plug_soc must be 1 to 99")
        out["auto_plug_soc"] = soc
    return out


def default_settings() -> dict:
    return {
        "power_entity": "", "soc_entity": "", "plug_entity": "",
        "auto_plug": False, "auto_plug_entity": "", "auto_plug_soc": DEFAULT_AUTO_PLUG_SOC,
    }


def _number(state: Optional[dict]) -> Optional[float]:
    if not state or str(state.get("state", "")).lower() in _UNKNOWN_STATES:
        return None
    try:
        return float(state["state"])
    except (TypeError, ValueError):
        return None


def power_kw(state: Optional[dict]) -> Optional[float]:
    """A power sensor's value in kW (W unless its unit says kW / MW)."""
    value = _number(state)
    if value is None:
        return None
    unit = str((state.get("attributes") or {}).get("unit_of_measurement") or "W").strip().lower()
    scale = {"kw": 1.0, "mw": 1000.0}.get(unit, 0.001)
    return value * scale


def soc_value(state: Optional[dict]) -> Optional[float]:
    value = _number(state)
    return value if value is not None and 0 <= value <= 100 else None


class HaLink:
    def __init__(
        self,
        data_dir: Optional[str],
        shared_state,
        set_power: Callable[[Optional[float]], None],
        set_soc: Callable[[Optional[float]], Awaitable[None]],
        plug: Callable[[], Awaitable[None]],
        token: Optional[str] = None,
    ) -> None:
        self._path = os.path.join(data_dir, "sensors.json") if data_dir else None
        self._shared = shared_state
        self._set_power = set_power
        self._set_soc = set_soc
        self._plug = plug
        self._token = token if token is not None else os.environ.get("SUPERVISOR_TOKEN", "")
        self.settings = default_settings()
        self.configured = False  # settings saved at least once (else: integration may migrate)
        self.states: dict[str, dict] = {}  # entity_id -> {"state", "attributes"}
        self.connected = False
        self.error: Optional[str] = None
        self._changed = asyncio.Event()
        self._entity_cache: tuple[float, list] = (0.0, [])
        self._reset_logic()
        self._load()

    # --- settings ------------------------------------------------------------

    def _load(self) -> None:
        if not self._path:
            return
        for path in (self._path, self._path + ".bak"):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                self.settings = validate_settings(data, default_settings())
                self.configured = True
                break
            except FileNotFoundError:
                continue
            except Exception:
                logger.warning("Sensor settings %s are unreadable", path)
        self._reset_logic()

    def _save(self) -> None:
        if not self._path:
            return
        try:
            tmp = self._path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=1)
                f.flush()
                os.fsync(f.fileno())
            if os.path.exists(self._path):
                os.replace(self._path, self._path + ".bak")
            os.replace(tmp, self._path)
        except Exception:
            logger.warning("Could not save sensor settings", exc_info=True)

    def _reset_logic(self) -> None:
        s = self.settings
        self.monitor_entity = s["auto_plug_entity"] or s["soc_entity"]
        self.auto_plug = AutoPlug(bool(s["auto_plug"] and self.monitor_entity), s["auto_plug_soc"])
        self.car_connected = CarConnected()

    async def update_settings(self, raw: dict) -> dict:
        new = validate_settings(raw, self.settings)
        self.settings = new
        self.configured = True
        self._save()
        self._reset_logic()
        logger.info(
            "Sensors: power %s, SoC %s, car plugged in %s, auto plug-in %s",
            new["power_entity"] or "-", new["soc_entity"] or "-", new["plug_entity"] or "-",
            f"below {new['auto_plug_soc']}% on {self.monitor_entity}" if self.auto_plug.enabled else "off",
        )
        # Apply what we already know; the resubscribe brings fresh states
        await self._apply_all(initial=True)
        self._changed.set()
        return new

    @property
    def watched(self) -> list[str]:
        s = self.settings
        ids = [s["power_entity"], s["soc_entity"], s["plug_entity"]]
        if self.auto_plug.enabled:
            ids.append(self.monitor_entity)
        return sorted({e for e in ids if e})

    # --- reacting to states ----------------------------------------------------

    async def _apply_all(self, initial: bool) -> None:
        for entity_id in self.watched or [""]:
            await self._entity_changed(entity_id, initial=initial)
        if not self.settings["power_entity"]:
            self._set_power(None)
        if not self.settings["soc_entity"]:
            await self._set_soc(None)

    async def _entity_changed(self, entity_id: str, initial: bool = False) -> None:
        s = self.settings
        state = self.states.get(entity_id)
        if entity_id and entity_id == s["power_entity"]:
            self._set_power(power_kw(state))
        if entity_id and entity_id == s["soc_entity"]:
            await self._set_soc(soc_value(state))
        plugged_in = bool(self._shared.plugged_in)
        if entity_id and entity_id == s["plug_entity"]:
            if self.car_connected.should_plug(state.get("state") if state else None, plugged_in):
                logger.info("%s turned on: switching Plugged In on", entity_id)
                await self._safe_plug()
                plugged_in = True
        if entity_id and self.auto_plug.enabled and entity_id == self.monitor_entity:
            soc = soc_value(state)
            if self.auto_plug.should_plug(soc, plugged_in):
                logger.info("Car SoC %.0f%% dropped below %d%%: switching Plugged In on", soc, s["auto_plug_soc"])
                if not await self._safe_plug():
                    self.auto_plug.armed = True  # try again on the next reading

    async def _safe_plug(self) -> bool:
        try:
            await self._plug()
            return True
        except Exception:
            logger.warning("Couldn't plug in", exc_info=True)
            return False

    async def handle_entities_event(self, event: dict) -> None:
        """A subscribe_entities event: a = added (full), c = changed (diff), r = removed."""
        changed: list[str] = []
        for entity_id, full in (event.get("a") or {}).items():
            self.states[entity_id] = {"state": full.get("s"), "attributes": full.get("a") or {}}
            changed.append(entity_id)
        for entity_id, diff in (event.get("c") or {}).items():
            current = self.states.setdefault(entity_id, {"state": None, "attributes": {}})
            plus = diff.get("+") or {}
            if "s" in plus:
                current["state"] = plus["s"]
            if "a" in plus:
                current["attributes"] = {**current["attributes"], **plus["a"]}
            for key in (diff.get("-") or {}).get("a") or []:
                current["attributes"].pop(key, None)
            changed.append(entity_id)
        for entity_id in event.get("r") or []:
            self.states.pop(entity_id, None)
            changed.append(entity_id)
        for entity_id in changed:
            await self._entity_changed(entity_id)

    # --- connection --------------------------------------------------------------

    @property
    def available(self) -> bool:
        return bool(self._token)

    async def run(self) -> None:
        """Stay connected to HA for the life of the add-on."""
        await self._apply_all(initial=True)
        if not self.available:
            self.error = "Not running under the Home Assistant Supervisor"
            logger.info("Home Assistant link off: %s", self.error)
            return
        import aiohttp

        attempt = 0
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    await self._connection(session)
                    attempt = 0
                except asyncio.CancelledError:
                    raise
                except Exception as err:
                    self.error = str(err) or type(err).__name__
                    logger.warning("Home Assistant link lost (%s); reconnecting", self.error)
                self.connected = False
                await asyncio.sleep(RECONNECT_DELAYS[min(attempt, len(RECONNECT_DELAYS) - 1)])
                attempt += 1

    async def _connection(self, session) -> None:
        import aiohttp

        async with session.ws_connect(SUPERVISOR_WS, heartbeat=30, max_msg_size=16 * 1024 * 1024) as ws:
            msg = await ws.receive_json(timeout=10)
            if msg.get("type") != "auth_required":
                raise RuntimeError(f"Unexpected greeting {msg.get('type')}")
            await ws.send_json({"type": "auth", "access_token": self._token})
            msg = await ws.receive_json(timeout=10)
            if msg.get("type") != "auth_ok":
                raise RuntimeError("Home Assistant refused the add-on's token")
            self.connected, self.error = True, None
            logger.info("Connected to Home Assistant")
            msg_id = 0
            sub_id: Optional[int] = None

            async def subscribe() -> None:
                nonlocal msg_id, sub_id
                if sub_id is not None:
                    msg_id += 1
                    await ws.send_json({"id": msg_id, "type": "unsubscribe_events", "subscription": sub_id})
                    sub_id = None
                # Fresh start: the subscription sends current states first
                self.states = {k: v for k, v in self.states.items() if k in self.watched}
                self.car_connected = CarConnected()
                self.auto_plug.armed = False
                if self.watched:
                    msg_id += 1
                    sub_id = msg_id
                    await ws.send_json({"id": msg_id, "type": "subscribe_entities", "entity_ids": self.watched})

            self._changed.clear()
            await subscribe()
            receive = None
            try:
                while True:
                    if receive is None:
                        receive = asyncio.ensure_future(ws.receive())
                    changed = asyncio.ensure_future(self._changed.wait())
                    done, _ = await asyncio.wait({receive, changed}, return_when=asyncio.FIRST_COMPLETED)
                    if changed in done:
                        self._changed.clear()
                        await subscribe()
                    else:
                        changed.cancel()
                    if receive not in done:
                        continue  # keep waiting on the same receive
                    raw, receive = receive.result(), None
                    await self._handle_frame(raw, sub_id)
            finally:
                if receive is not None:
                    receive.cancel()

    async def _handle_frame(self, raw, sub_id) -> None:
        import aiohttp

        if raw.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.ERROR):
            raise ConnectionError("Home Assistant closed the connection")
        if raw.type != aiohttp.WSMsgType.TEXT:
            return
        data = json.loads(raw.data)
        for message in data if isinstance(data, list) else [data]:
            if message.get("type") == "event" and message.get("id") == sub_id:
                await self.handle_entities_event(message.get("event") or {})
            elif message.get("type") == "result" and not message.get("success", True):
                logger.warning("Home Assistant: %s", (message.get("error") or {}).get("message"))

    async def list_entities(self) -> list[dict]:
        """Sensors and binary sensors for the pickers (cached briefly)."""
        cached_at, cached = self._entity_cache
        if cached and time.monotonic() - cached_at < ENTITY_LIST_TTL_S:
            return cached
        if not self.available:
            return []
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{SUPERVISOR_API}/states",
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                resp.raise_for_status()
                states = await resp.json()
        out = []
        for st in states:
            entity_id = st.get("entity_id", "")
            domain = entity_id.split(".", 1)[0]
            if domain not in ("sensor", "binary_sensor"):
                continue
            attrs = st.get("attributes") or {}
            out.append({
                "entity_id": entity_id,
                "name": attrs.get("friendly_name") or entity_id,
                "device_class": attrs.get("device_class"),
                "unit": attrs.get("unit_of_measurement"),
                "state": st.get("state"),
            })
        out.sort(key=lambda e: (e["name"] or "").lower())
        self._entity_cache = (time.monotonic(), out)
        return out

    # --- status ------------------------------------------------------------------

    def snapshot(self) -> dict:
        s = self.settings

        def entity(entity_id: str) -> Optional[dict]:
            if not entity_id:
                return None
            st = self.states.get(entity_id)
            attrs = (st or {}).get("attributes") or {}
            return {
                "entity_id": entity_id,
                "name": attrs.get("friendly_name") or entity_id,
                "state": (st or {}).get("state"),
                "unit": attrs.get("unit_of_measurement"),
            }

        monitor = entity(self.monitor_entity) if self.monitor_entity else None
        return {
            "settings": s,
            "configured": self.configured,
            "available": self.available,
            "connected": self.connected,
            "error": self.error,
            "power": {
                "entity": entity(s["power_entity"]),
                "kw": power_kw(self.states.get(s["power_entity"])) if s["power_entity"] else None,
                "source": self._shared.power_source,
            },
            "reporting_soc": {
                "entity": entity(s["soc_entity"]),
                "soc": self._shared.soc_percent,
            },
            "plug": {
                "entity": entity(s["plug_entity"]),
                "last": self.car_connected.last,
            },
            "monitored_soc": {
                "entity": monitor,
                "soc": soc_value(self.states.get(self.monitor_entity)) if self.monitor_entity else None,
                "source": None if not self.monitor_entity else (
                    "monitor sensor" if s["auto_plug_entity"] else "reporting SoC sensor"
                ),
                "auto_plug": self.auto_plug.enabled,
                "threshold": s["auto_plug_soc"],
                "armed": self.auto_plug.armed,
            },
        }
