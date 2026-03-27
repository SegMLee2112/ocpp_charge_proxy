from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys

import websockets
from aiohttp import web

from src.api import create_api_app
from src.client import ChargePoint
from src.config import load_config
from src.console import console_loop
from src.persistence import Persistence
from src.shared_state import SharedState

logger = logging.getLogger("ocpp_charge_proxy")

BACKOFF_STEPS = [5, 10, 30, 60, 300]


async def run() -> None:
    config = load_config()

    log_level = getattr(logging, config.log_level.upper(), logging.INFO)
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    logging.basicConfig(
        level=log_level,
        format=log_format,
        stream=sys.stdout,
    )

    data_dir = os.environ.get("IO_DATA_DIR", "/data")
    os.makedirs(data_dir, exist_ok=True)

    logger.info("Starting OCPP Charge Proxy, connecting to %s", config.redacted_url)

    persistence = Persistence(data_dir=data_dir)

    # Seed energy register if initial_energy_wh is set (cleared by s6 run script)
    if config.initial_energy_wh > 0:
        persistence.save_energy_register_wh(config.initial_energy_wh)
        logger.info("Energy register set to %d Wh from config", config.initial_energy_wh)

    shared_state = SharedState()

    # --- Command callbacks for the API ---
    async def do_plug():
        from ocpp.v16.enums import ChargePointStatus as CPS
        if cp is None:
            return
        # Bug 5 fix: don't plug if already plugged in or charging
        if cp.state in (CPS.preparing, CPS.charging, CPS.suspended_ev, CPS.suspended_evse):
            return
        cp.state = CPS.preparing
        shared_state.state = cp.state
        shared_state.plugged_in = True
        try:
            await cp.send_status()
        except Exception:
            logger.warning("Failed to send status after plug", exc_info=True)

    async def do_unplug():
        from ocpp.v16.enums import ChargePointStatus as CPS
        if cp is None:
            return
        # Set unplugged state immediately so the integration sees it
        shared_state.plugged_in = False
        shared_state.state = CPS.available
        if cp._transaction_id is not None:
            # Bug 3 fix: pass final_state so _do_stop_transaction doesn't clobber
            await cp._do_stop_transaction(final_state=CPS.available)
        cp.state = CPS.available
        shared_state.state = cp.state
        try:
            await cp.send_status()
        except Exception:
            logger.warning("Failed to send status after unplug", exc_info=True)

    async def do_set_current(amps: int):
        if cp is not None:
            cp._charger_sim.current_amps = amps
            shared_state.current_amps_setting = amps

    async def do_set_power(power_kw: float | None):
        if cp is not None:
            cp._power_override = power_kw

    api_app = create_api_app(shared_state, do_plug, do_unplug, do_set_current, do_set_power)
    runner = web.AppRunner(api_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8099)
    await site.start()
    logger.info("API server started on port 8099")

    attempt = 0
    cp = None
    try:
      while True:
        try:
            async with websockets.connect(
                config.websocket_url,
                subprotocols=["ocpp1.6"],
            ) as ws:
                attempt = 0
                logger.info("Connected to OCPP server")

                cp = ChargePoint(
                    id=config.chargepoint_id,
                    connection=ws,
                    persistence=persistence,
                    current_amps=config.current_amps,
                    shared_state=shared_state,
                )

                # Start message loop first so incoming messages are handled
                start_task = asyncio.create_task(cp.start())

                # Use configured serial, or generate/load a persistent one
                serial = config.charger_serial or persistence.load_serial_number()

                interval = await cp.send_boot_notification(
                    model=config.charger_model,
                    vendor=config.charger_vendor,
                    serial_number=serial,
                    firmware_version=config.firmware_version,
                )

                tasks = [
                    start_task,
                    cp.heartbeat_loop(interval),
                    cp.meter_values_loop(),
                ]

                # Run interactive console when stdin is a terminal
                if sys.stdin.isatty():
                    tasks.append(console_loop(cp, do_plug, do_unplug, do_set_current))

                await asyncio.gather(*tasks)

        except (
            websockets.exceptions.ConnectionClosed,
            websockets.exceptions.WebSocketException,
            OSError,
        ) as e:
            cp = None  # prevent stale cp access during reconnection
            shared_state.connected_to_server = False
            backoff = BACKOFF_STEPS[min(attempt, len(BACKOFF_STEPS) - 1)]
            logger.warning(
                "Connection lost (%s), reconnecting in %ds...", e, backoff,
            )
            attempt += 1
            await asyncio.sleep(backoff)
        except SystemExit:
            logger.info("Shutting down, sending Unavailable status")
            try:
                if cp is not None:
                    await cp.send_status_unavailable()
            except Exception:
                pass
            break
    finally:
        await runner.cleanup()



def _handle_sigterm(*args):
    logger.info("SIGTERM received")
    raise SystemExit("SIGTERM")


def main():
    signal.signal(signal.SIGTERM, _handle_sigterm)
    asyncio.run(run())


if __name__ == "__main__":
    main()
