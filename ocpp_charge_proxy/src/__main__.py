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

# s6-overlay gives services ~3s after SIGTERM before SIGKILL, so the goodbye
# messages to the server must fit comfortably inside that window.
SHUTDOWN_STOP_TX_TIMEOUT = 1.5
SHUTDOWN_STATUS_TIMEOUT = 1.0


async def _graceful_shutdown(cp: ChargePoint) -> None:
    """Tell the server we're going away, while the socket is still open."""
    from ocpp.v16.enums import ChargePointStatus as CPS, Reason

    logger.info("Shutting down: notifying OCPP server")
    if cp._transaction_id is not None:
        try:
            await asyncio.wait_for(
                cp._do_stop_transaction(
                    final_state=CPS.unavailable, reason=Reason.reboot,
                ),
                SHUTDOWN_STOP_TX_TIMEOUT,
            )
        except Exception:
            logger.warning("Could not stop transaction during shutdown", exc_info=True)
    try:
        await asyncio.wait_for(cp.send_status_unavailable(), SHUTDOWN_STATUS_TIMEOUT)
        logger.info("Sent Unavailable status to server")
    except Exception:
        logger.warning("Could not send Unavailable status during shutdown", exc_info=True)


async def _cancel_all(tasks) -> None:
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


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
        if persistence.seed_energy_register_wh(config.initial_energy_wh):
            logger.info("Energy register set to %d Wh from config", config.initial_energy_wh)
        else:
            logger.warning(
                "initial_energy_wh=%d ignored: stored energy register is already "
                "%d Wh and the meter must never go backwards. Set the option to 0.",
                config.initial_energy_wh, persistence.load_energy_register_wh(),
            )

    shared_state = SharedState()
    # Report the stored energy register from the start. The API comes up
    # before the first meter reading; serving the default 0 meant HA's
    # total_increasing Energy sensor saw stored -> 0 -> stored on every restart
    # and recorded the whole register as new consumption.
    shared_state.energy_kwh = persistence.load_energy_register_wh() / 1000.0

    # SIGTERM/SIGINT are handled inside the event loop so shutdown runs as
    # normal async code (a plain signal.signal handler raising SystemExit
    # fires outside our coroutines and kills the process before we can
    # notify the server).
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _on_signal(sig: signal.Signals) -> None:
        logger.info("%s received", sig.name)
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _on_signal, sig)
        except (NotImplementedError, RuntimeError):
            pass  # e.g. Windows dev runs — fall back to default behaviour

    stop_task = asyncio.create_task(stop_event.wait())

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
            from ocpp.v16.enums import Reason
            await cp._do_stop_transaction(
                final_state=CPS.available, reason=Reason.ev_disconnected,
            )
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
      while not stop_event.is_set():
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

                boot_task = asyncio.create_task(cp.send_boot_notification(
                    model=config.charger_model,
                    vendor=config.charger_vendor,
                    serial_number=serial,
                    firmware_version=config.firmware_version,
                ))
                await asyncio.wait(
                    {boot_task, stop_task}, return_when=asyncio.FIRST_COMPLETED,
                )
                if not boot_task.done():
                    # Shutdown requested while still booting
                    await _cancel_all([boot_task, start_task])
                    break
                try:
                    interval = boot_task.result()
                except BaseException:
                    await _cancel_all([start_task])
                    raise

                tasks = [
                    start_task,
                    asyncio.create_task(cp.heartbeat_loop(interval)),
                    asyncio.create_task(cp.meter_values_loop()),
                    asyncio.create_task(cp.clock_aligned_loop()),
                ]

                # Run interactive console when stdin is a terminal
                if sys.stdin.isatty():
                    tasks.append(asyncio.create_task(
                        console_loop(cp, do_plug, do_unplug, do_set_current)
                    ))

                # Wait until ANY task ends (normally the message loop when the
                # socket closes), then cancel the rest. asyncio.gather() does
                # not cancel siblings on failure, which left the old
                # connection's heartbeat/meter loops running forever after a
                # reconnect ("Heartbeat cycle failed ... ConnectionClosedOK").
                try:
                    done, _ = await asyncio.wait(
                        [*tasks, stop_task], return_when=asyncio.FIRST_COMPLETED,
                    )
                    if stop_task in done:
                        # Message loop is still running here, so the server's
                        # replies to our goodbye messages can be received.
                        await _graceful_shutdown(cp)
                finally:
                    await _cancel_all(tasks)

                if stop_task in done:
                    break

                for t in done:
                    exc = t.exception()
                    if exc is not None:
                        raise exc

                # Message loop returned cleanly — server closed with 1000 (OK).
                # Treat as a lost connection and reconnect.
                raise websockets.exceptions.ConnectionClosedOK(None, None)

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
            # Sleep for the backoff, but wake immediately on shutdown
            try:
                await asyncio.wait_for(asyncio.shield(stop_task), backoff)
            except asyncio.TimeoutError:
                pass
        except SystemExit as e:
            # e.g. BootNotification rejected by the server
            logger.info("Shutting down: %s", e)
            break
    finally:
        stop_task.cancel()
        await runner.cleanup()
        logger.info("OCPP Charge Proxy stopped")


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
