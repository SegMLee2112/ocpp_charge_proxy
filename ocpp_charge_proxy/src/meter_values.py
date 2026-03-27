from __future__ import annotations

import datetime

from src.charger_sim import ChargerReading


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sv(value: str, measurand: str, context: str, unit: str | None = None) -> dict:
    """Build a single sampled value with full OCPP metadata."""
    entry = {
        "format": "Raw",
        "location": "Outlet",
        "context": context,
        "measurand": measurand,
        "value": value,
    }
    if unit is not None:
        entry["unit"] = unit
    return entry


def build_idle_meter_values(energy_register_wh: int) -> list[dict]:
    """Periodic meter values when idle (not charging)."""
    ctx = "Sample.Periodic"
    return [
        {
            "timestamp": _now_iso(),
            "sampledValue": [
                _sv(str(float(energy_register_wh)), "Energy.Active.Import.Register", ctx, "Wh"),
                _sv("0.0", "Power.Active.Import", ctx, "W"),
                _sv("0", "Energy.Active.Export.Register", ctx, "Wh"),
                _sv("0", "Power.Active.Export", ctx, "W"),
            ],
        }
    ]


def build_charging_meter_values(
    reading: ChargerReading,
    energy_register_wh: int,
) -> list[dict]:
    """Periodic meter values during active charging."""
    ctx = "Sample.Periodic"
    return [
        {
            "timestamp": _now_iso(),
            "sampledValue": [
                _sv(str(float(energy_register_wh)), "Energy.Active.Import.Register", ctx, "Wh"),
                _sv(str(round(reading.power_kw * 1000, 1)), "Power.Active.Import", ctx, "W"),
                _sv(str(reading.frequency_hz), "Frequency", ctx),
                _sv(str(round(reading.power_offered_kw * 1000)), "Power.Offered", ctx, "W"),
                _sv(str(reading.current_offered_a), "Current.Offered", ctx, "A"),
                _sv("0", "Energy.Active.Export.Register", ctx, "Wh"),
                _sv("0", "Power.Active.Export", ctx, "W"),
            ],
        }
    ]