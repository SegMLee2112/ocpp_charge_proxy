from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    server_hostname: str
    chargepoint_id: str
    password: str
    charger_model: str
    charger_vendor: str
    charger_serial: str
    firmware_version: str
    current_amps: int
    initial_energy_wh: int
    log_level: str
    use_tls: bool = True
    start_delay_s: float = 3.0  # car waits this long after StartTransaction
    ramp_up_s: float = 5.0  # then ramps 0 -> full power over this long
    replug_enabled: bool = True  # see src/automation.py
    replug_after_min: int = 10
    replug_attempts: int = 3

    @property
    def websocket_url(self) -> str:
        scheme = "wss" if self.use_tls else "ws"
        return f"{scheme}://{self.chargepoint_id}:{self.password}@{self.server_hostname}/{self.chargepoint_id}"

    @property
    def redacted_url(self) -> str:
        scheme = "wss" if self.use_tls else "ws"
        return f"{scheme}://{self.chargepoint_id}:***@{self.server_hostname}/{self.chargepoint_id}"


def _env_float(name: str, default: float) -> float:
    """Non-negative float from the environment; blank/"null"/invalid -> default."""
    raw = os.environ.get(name, "").strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        return default


def _env_int(name: str, default: int, low: int, high: int) -> int:
    """Whole number from the environment within [low, high]; blank/invalid -> default."""
    raw = os.environ.get(name, "").strip()
    try:
        return min(high, max(low, int(float(raw))))
    except ValueError:
        return default


def load_config() -> Config:
    return Config(
        server_hostname=os.environ["IO_SERVER_HOSTNAME"],
        chargepoint_id=os.environ["IO_CHARGEPOINT_ID"],
        password=os.environ["IO_PASSWORD"],
        charger_model=os.environ.get("IO_CHARGER_MODEL", "PLP2-0-2-2"),
        charger_vendor=os.environ.get("IO_CHARGER_VENDOR", "Wall Box Chargers"),
        charger_serial=os.environ.get("IO_CHARGER_SERIAL", ""),
        firmware_version=os.environ.get("IO_FIRMWARE_VERSION", "6.11.16"),
        current_amps=int(os.environ.get("IO_CURRENT_AMPS", "32")),
        initial_energy_wh=int(os.environ.get("IO_INITIAL_ENERGY_WH", "0")),
        log_level=os.environ.get("IO_LOG_LEVEL", "info"),
        use_tls=os.environ.get("IO_USE_TLS", "true").lower() != "false",
        start_delay_s=_env_float("IO_START_DELAY_S", 3.0),
        ramp_up_s=_env_float("IO_RAMP_UP_S", 5.0),
        replug_enabled=os.environ.get("IO_REPLUG_ENABLED", "true").strip().lower() not in ("false", "0", "no", "off"),
        replug_after_min=_env_int("IO_REPLUG_AFTER_MIN", 10, 1, 240),
        replug_attempts=_env_int("IO_REPLUG_ATTEMPTS", 3, 0, 20),
    )


def starting_current_amps(config: Config, persistence) -> int:
    """The HA max current saved last time, unless the add-on option changed since.

    Changing current_amps in the add-on configuration is an explicit choice, so
    it takes over again; otherwise the setting made in Home Assistant is kept.
    """
    saved = persistence.load_current_setting()
    if saved and saved.get("option") == config.current_amps:
        try:
            return int(saved["amps"])
        except (TypeError, ValueError):
            pass
    return config.current_amps
