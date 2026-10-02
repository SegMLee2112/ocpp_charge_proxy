from __future__ import annotations

import asyncio
import json
import logging
import time
import os
from pathlib import Path
from typing import Callable, Awaitable

from aiohttp import web

from src.charger_sim import VALID_CURRENT_SETTINGS
from src.shared_state import SharedState

logger = logging.getLogger(__name__)


def create_api_app(
    shared_state: SharedState,
    on_plug: Callable[[], Awaitable[None]],
    on_unplug: Callable[[], Awaitable[None]],
    on_set_current: Callable[[int], Awaitable[None]],
    on_set_power: Callable[[float | None], Awaitable[None]] | None = None,
    on_refresh: Callable[[], None] | None = None,
    on_set_soc: Callable[[float | None], Awaitable[None]] | None = None,
) -> web.Application:
    app = web.Application()
    app["shared_state"] = shared_state
    app["on_plug"] = on_plug
    app["on_unplug"] = on_unplug
    app["on_set_current"] = on_set_current
    app["on_set_power"] = on_set_power
    app["on_refresh"] = on_refresh
    app["on_set_soc"] = on_set_soc
    app["events_stop"] = asyncio.Event()
    app.on_shutdown.append(_close_event_streams)

    # Ingress serves the status page — use relative path for API calls
    static_dir = Path(__file__).parent / "static"
    app.router.add_get("/", handle_index)
    app["static_dir"] = static_dir
    app.router.add_get("/api/state", handle_get_state)
    app.router.add_post("/api/plug", handle_plug)
    app.router.add_post("/api/unplug", handle_unplug)
    app.router.add_post("/api/current", handle_current)
    app.router.add_post("/api/power", handle_power)
    app.router.add_post("/api/soc", handle_soc)
    app.router.add_get("/api/events", handle_events)

    return app


async def handle_index(request: web.Request) -> web.Response:
    static_dir: Path = request.app["static_dir"]
    index = static_dir / "index.html"
    return web.FileResponse(index)


async def handle_get_state(request: web.Request) -> web.Response:
    state: SharedState = request.app["shared_state"]
    on_refresh = request.app["on_refresh"]
    if on_refresh is not None:
        try:
            on_refresh()  # live power, not just the last meter reading
        except Exception:
            logger.debug("Live power refresh failed", exc_info=True)
    return web.json_response(state.to_dict())


async def handle_plug(request: web.Request) -> web.Response:
    await request.app["on_plug"]()
    return web.json_response({"status": "ok"})


async def handle_unplug(request: web.Request) -> web.Response:
    await request.app["on_unplug"]()
    return web.json_response({"status": "ok"})


async def handle_current(request: web.Request) -> web.Response:
    try:
        body = await request.json()
        amps = int(body["amps"])
    except (ValueError, KeyError, Exception):
        return web.json_response(
            {"status": "error", "message": "Invalid request. Send JSON: {\"amps\": N}"},
            status=400,
        )
    if amps not in VALID_CURRENT_SETTINGS:
        return web.json_response(
            {"status": "error", "message": f"Invalid current. Valid: {VALID_CURRENT_SETTINGS}"},
            status=400,
        )
    await request.app["on_set_current"](amps)
    return web.json_response({"status": "ok"})


async def handle_power(request: web.Request) -> web.Response:
    on_set_power = request.app["on_set_power"]
    if on_set_power is None:
        return web.json_response(
            {"status": "error", "message": "Power override not supported"},
            status=501,
        )
    try:
        body = await request.json()
        power_kw = body.get("power_kw")
        if power_kw is not None:
            power_kw = float(power_kw)
    except (ValueError, Exception):
        return web.json_response(
            {"status": "error", "message": "Invalid request. Send JSON: {\"power_kw\": N} or {\"power_kw\": null}"},
            status=400,
        )
    await on_set_power(power_kw)
    return web.json_response({"status": "ok"})


async def handle_soc(request: web.Request) -> web.Response:
    """Car state of charge (%) from the integration; null = unknown / not set."""
    on_set_soc = request.app["on_set_soc"]
    if on_set_soc is None:
        return web.json_response(
            {"status": "error", "message": "SoC not supported"}, status=501,
        )
    try:
        body = await request.json()
        soc = body.get("soc")
        if soc is not None:
            soc = float(soc)
            if not 0 <= soc <= 100:
                raise ValueError("soc must be 0-100")
    except (ValueError, TypeError, AttributeError, json.JSONDecodeError):
        return web.json_response(
            {"status": "error", "message": "Invalid request. Send JSON: {\"soc\": 0-100} or {\"soc\": null}"},
            status=400,
        )
    await on_set_soc(soc)
    return web.json_response({"status": "ok"})


# --- Push updates (Server-Sent Events) -------------------------------------

# Fields that change on every live-power refresh: pushed at most every
# EVENTS_LIVE_INTERVAL seconds, so HA's recorder isn't flooded. Any other
# change (state, plug, connection, energy, commands...) is pushed at once.
_LIVE_FIELDS = {
    "power_kw", "voltage", "current_a", "frequency_hz", "power_offered_kw",
    "power_entity_value",
}
EVENTS_CHECK_INTERVAL = 1.0
EVENTS_LIVE_INTERVAL = 10.0


def _significant(data: dict) -> dict:
    return {k: v for k, v in data.items() if k not in _LIVE_FIELDS}


def _state_snapshot(app: web.Application) -> dict:
    on_refresh = app["on_refresh"]
    if on_refresh is not None:
        try:
            on_refresh()
        except Exception:
            logger.debug("Live power refresh failed", exc_info=True)
    return app["shared_state"].to_dict()


async def handle_events(request: web.Request) -> web.StreamResponse:
    """Stream the state to the integration as Server-Sent Events.

    One event straight away, then on every significant change (within ~1s),
    and at least every EVENTS_LIVE_INTERVAL seconds with live power (which
    also keeps the connection alive).
    """
    app = request.app
    stop: asyncio.Event = app["events_stop"]
    resp = web.StreamResponse(headers={
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })
    await resp.prepare(request)
    last_sig = None
    last_sent = 0.0
    try:
        while not stop.is_set():
            sig = _significant(app["shared_state"].to_dict())
            now = time.monotonic()
            if sig != last_sig or now - last_sent >= EVENTS_LIVE_INTERVAL:
                data = _state_snapshot(app)
                await resp.write(f"data: {json.dumps(data, default=str)}\n\n".encode())
                last_sig = _significant(data)
                last_sent = now
            try:
                await asyncio.wait_for(stop.wait(), EVENTS_CHECK_INTERVAL)
            except asyncio.TimeoutError:
                pass
    except (ConnectionResetError, ConnectionError):
        pass  # integration went away
    return resp


async def _close_event_streams(app: web.Application) -> None:
    """End open event streams so add-on shutdown isn't held up by them."""
    app["events_stop"].set()
