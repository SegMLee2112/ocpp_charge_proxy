from __future__ import annotations

import logging
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
) -> web.Application:
    app = web.Application()
    app["shared_state"] = shared_state
    app["on_plug"] = on_plug
    app["on_unplug"] = on_unplug
    app["on_set_current"] = on_set_current
    app["on_set_power"] = on_set_power
    app["on_refresh"] = on_refresh

    # Ingress serves the status page — use relative path for API calls
    static_dir = Path(__file__).parent / "static"
    app.router.add_get("/", handle_index)
    app["static_dir"] = static_dir
    app.router.add_get("/api/state", handle_get_state)
    app.router.add_post("/api/plug", handle_plug)
    app.router.add_post("/api/unplug", handle_unplug)
    app.router.add_post("/api/current", handle_current)
    app.router.add_post("/api/power", handle_power)

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
