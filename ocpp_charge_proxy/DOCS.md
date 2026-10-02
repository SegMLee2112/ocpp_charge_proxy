# Home Assistant Add-on: OCPP Charge Proxy

## How to use

This add-on acts as a virtual OCPP 1.6 chargepoint and connects to any
OCPP 1.6J server. When the server sends charge scheduling commands, the add-on
updates its state so Home Assistant automations can respond.

## Prerequisites

- An OCPP 1.6J compatible provider account (or any CSMS that accepts OCPP 1.6
  chargepoint connections)
- OCPP connection credentials (server hostname, chargepoint ID, password)
  from your provider

## Configuration

### Required options

| Option | Description |
|--------|-------------|
| `server_hostname` | Your provider's OCPP server hostname |
| `chargepoint_id` | Your chargepoint ID for authentication |
| `password` | Your OCPP password |

### Optional options

| Option | Default | Description |
|--------|---------|-------------|
| `charger_model` | `PLP2-0-2-2` | Charger model reported in BootNotification |
| `charger_vendor` | `Wall Box Chargers` | Charger vendor reported in BootNotification |
| `charger_serial` | Auto-generated | Charger serial number (generated on first boot if empty) |
| `firmware_version` | `6.11.16` | Firmware version reported in BootNotification |
| `current_amps` | `32` | Maximum charging current in amps (6/10/13/16/20/25/32) |
| `initial_energy_wh` | `0` | Seed the energy register (Wh). Set to your old charger's meter reading when migrating. Only applied if higher than the stored register (the meter never goes backwards); cleared after first boot. |
| `start_delay_s` | `3` | Seconds after StartTransaction before the simulated car draws any current (also applied when resuming after a charging-profile pause). `0` = instant. |
| `ramp_up_s` | `5` | Seconds for power to ramp linearly from 0 to full after the start delay. `0` = jump straight to full power. Not applied when power comes from a real power entity. |
| `log_level` | `info` | Logging level (debug/info/warning/error) |

### Controlling your charger

Use the companion integration's **State** sensor to trigger automations when
your provider starts or stops charging. For example, create an automation that
turns on a smart plug when the state changes to `Charging` and turns it off
when it changes to `Preparing` or `Available`.

### Power entity

You can optionally configure a Home Assistant power sensor in the companion
integration's settings. The proxy will report this real power value to your
provider instead of simulating power delivery. The value is capped at what the
virtual chargepoint could physically deliver at its current setting.

If not configured, the proxy uses a realistic power simulation.

## How it works

1. The add-on connects to your provider's OCPP server via WebSocket
2. It registers as a chargepoint (BootNotification)
3. It sends periodic heartbeats and meter values
4. When you "plug in" via the companion integration, it reports `Preparing`
5. Your provider creates a charge schedule and sends `RemoteStartTransaction`
6. The proxy transitions through `SuspendedEV` -> `Charging` and reports
   meter values
7. When the provider ends the session, it sends `RemoteStopTransaction`
8. The proxy reports `Finishing` then returns to `Preparing`

If the connection drops, the add-on automatically reconnects with exponential
backoff.

## Companion Integration

Install the companion integration via HACS to get proper HA entities:

1. Add this repository to HACS as a custom repository (Integration category)
2. Install "OCPP Charge Proxy" from HACS
3. Restart Home Assistant
4. The integration should auto-discover the add-on. If not, go to
   Settings > Devices & Services > Add Integration > OCPP Charge Proxy

### Entities provided

| Entity | Type | Description |
|--------|------|-------------|
| Plugged In | Switch | Simulate car plugged in/unplugged |
| Current Amps Setting | Select | Set charger current (6-32A) |
| State | Sensor | OCPP state (Available/Preparing/Charging/etc.) |
| Power | Sensor | Current power draw (kW) |
| Energy | Sensor | Cumulative energy (kWh, works with energy dashboard) |
| Current | Sensor | Current draw (A) |
| Power Source | Sensor | Whether using real entity or simulated values |
| Connected to Server | Binary Sensor | Connected to OCPP server |

### Integration options

In the integration's settings (Configure), you can optionally set a **power
sensor** entity. This should be a sensor that reports power in watts (W), such
as your battery charge power or grid demand sensor.

## Getting your OCPP credentials

Your provider will supply three values needed to connect:

- **Server hostname** — the OCPP WebSocket endpoint
- **Chargepoint ID** — your unique chargepoint identifier
- **Password** — authentication password

You may also need to set `charger_model` and `charger_vendor` to match a
charger model your provider supports. The defaults work for providers that
accept Wallbox chargepoints.

Check your provider's app or documentation for how to obtain these credentials.
