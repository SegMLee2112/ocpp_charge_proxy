from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class SharedState:
    """State shared between the OCPP client and the REST API."""

    state: str = "Available"
    plugged_in: bool = False
    power_kw: float = 0.0
    voltage: float = 230.0
    current_a: float = 0.0
    frequency_hz: float = 50.0
    power_offered_kw: float = 0.0
    energy_kwh: float = 0.0
    current_amps_setting: int = 32  # HA max current (the select)
    current_amps_effective: int = 32  # what the charger actually uses
    current_amps_provider_limit: Optional[float] = None  # chargingALimitConn1
    transaction_id: Optional[int] = None
    connected_to_server: bool = False
    meter_interval: int = 60
    power_source: str = "simulated"
    power_entity_value: Optional[float] = None
    server_config: dict[str, str] = field(default_factory=dict)
    # Last OCPP command from the server, and last message we sent (Heartbeat
    # and MeterValues excluded): {action, timestamp, payload, status, response}
    last_command_received: Optional[dict] = None
    last_command_sent: Optional[dict] = None
    # Car's state of charge (%) from the integration's SoC entity, None if unset
    soc_percent: Optional[float] = None
    # Transaction messages waiting to be sent (offline queue)
    held_messages: int = 0

    def to_dict(self) -> dict:
        return asdict(self)
