from __future__ import annotations

import asyncio
import logging
import sys
from typing import Callable, Awaitable

from ocpp.v16.enums import ChargePointStatus

from src.client import ChargePoint

logger = logging.getLogger(__name__)

from src.charger_sim import VALID_CURRENT_SETTINGS

HELP_TEXT = f"""
Commands:
  plug          - Simulate car plugged in (Preparing)
  unplug        - Simulate car unplugged (Available)
  current <n>   - Set charger current ({'/'.join(str(a) for a in VALID_CURRENT_SETTINGS)}A)
  status        - Show current state
  config        - Show server configuration
  profile       - Show active charging profile
  help          - Show this help
  quit          - Shutdown gracefully
"""


async def console_loop(
    cp: ChargePoint,
    on_plug: Callable[[], Awaitable[None]],
    on_unplug: Callable[[], Awaitable[None]],
    on_set_current: Callable[[int], Awaitable[None]],
) -> None:
    """Interactive CLI for controlling the proxy state."""
    print(HELP_TEXT)
    print(f"Current state: {cp.state}")
    print()

    loop = asyncio.get_event_loop()

    while True:
        try:
            line = await loop.run_in_executor(None, lambda: input("io> "))
        except EOFError:
            break

        line = line.strip().lower()
        if not line:
            continue

        parts = line.split()
        cmd = parts[0]

        try:
            if cmd == "plug":
                await on_plug()
                print(f"State -> Preparing (car plugged in)")

            elif cmd == "unplug":
                await on_unplug()
                print(f"State -> Available (car unplugged)")

            elif cmd == "current":
                if len(parts) < 2:
                    print(f"Usage: current <amps>  (valid: {VALID_CURRENT_SETTINGS})")
                    continue
                amps = int(parts[1])
                await on_set_current(amps)
                print(f"Current set to {amps}A (~{cp._charger_sim.rated_power_kw} kW)")

            elif cmd == "status":
                sim = cp._charger_sim
                print(f"  State:          {cp.state}")
                print(f"  Current:        {sim.current_amps}A (~{sim.rated_power_kw} kW)")
                print(f"  Transaction ID: {cp._transaction_id}")
                print(f"  Energy (Wh):    {cp._energy_register_wh}")
                print(f"  Energy (kWh):   {cp.energy_register_kwh:.3f}")
                print(f"  Meter interval: {cp._meter_value_interval}s")

            elif cmd == "profile":
                limit = cp._profile_scheduler.get_current_limit_kw()
                print(cp._profile_scheduler.profile_summary)
                if limit is not None:
                    print(f"  Current limit: {limit:.1f} kW {'(paused)' if limit <= 0 else ''}")
                else:
                    print("  Current limit: none (rated power)")

            elif cmd == "config":
                if cp._server_config:
                    for key, value in cp._server_config.items():
                        print(f"  {key} = {value}")
                else:
                    print("  No server config received yet")

            elif cmd == "help":
                print(HELP_TEXT)

            elif cmd in ("quit", "exit"):
                raise SystemExit("User quit")

            else:
                print(f"Unknown command: {cmd}. Type 'help' for available commands.")

        except SystemExit:
            raise
        except Exception as e:
            print(f"Error: {e}")
            logger.warning("Console command failed", exc_info=True)
