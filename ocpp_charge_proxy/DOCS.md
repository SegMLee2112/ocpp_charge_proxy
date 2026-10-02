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
| `current_amps` | `32` | Maximum charging current in amps (6/10/13/16/20/25/32). Starting value: once you change Max current on the add-on's web page that's remembered, until you change this option again |
| `initial_energy_wh` | `0` | Seed the energy register (Wh). Set to your old charger's meter reading when migrating. Only applied if higher than the stored register (the meter never goes backwards); cleared after first boot. |
| `start_delay_s` | `3` | Seconds after StartTransaction before the simulated car draws any current (also applied when resuming after a charging-profile pause). `0` = instant. |
| `ramp_up_s` | `5` | Seconds for power to ramp linearly from 0 to full after the start delay. `0` = jump straight to full power. Not applied when power comes from a real power entity. |
| `replug_enabled` | `true` | Auto re-plug: if your provider hasn't started a session `replug_after_min` minutes after Plugged In turns on, unplug for 30 seconds and plug back in |
| `replug_after_min` | `10` | Minutes plugged in with no session before re-plugging (1–240) |
| `replug_attempts` | `3` | Re-plug tries before giving up until the car is next unplugged or a session starts (0–20) |
| `log_level` | `info` | Logging level (debug/info/warning/error). OCPP messages are logged at `info`, except Heartbeats and periodic meter readings (in a session or not), which only show at `debug`. Clock-aligned readings stay at `info` |

### Controlling your charger

Use the companion integration's **Power** sensor to trigger automations when
your provider starts or stops charging: with the simulated power, it's above
0 while the charger is charging. For example, turn on a smart plug when it
rises above 0 and off when it drops back to 0.

### Power entity

You can optionally pick a Home Assistant power sensor (W or kW) on the
add-on's **Simulation** tab. The proxy will report this real power value to your
provider instead of simulating power delivery. The value is capped at what the
virtual chargepoint could physically deliver at its current setting.

If not configured, the proxy uses a realistic power simulation.

### SoC sensor for reporting

You can also pick a **SoC sensor** on the Simulation tab, for example from
your car's own integration, reporting 0–100%. When set:

- The car's state of charge is sent to your provider whenever it asks for
  `SoC` in its meter values (Octopus does), while a car is plugged in.
- **Car full:** when the sensor reads 100% during a session, the charger
  reports `SuspendedEV` and stops drawing power, as a real car does when its
  battery is full. The session stays open; if the SoC drops below 100%,
  charging resumes. A charging-profile pause (`SuspendedEVSE`) takes priority.

Leave it unset (or clear it) and no SoC is reported and car-full never
triggers. If the sensor becomes unavailable, SoC reporting pauses until it
comes back.

### Schedule and auto re-plug

On the add-on's **Automation** tab:

- **Schedule:** add as many times as you like, each with a time, the days
  it runs on, and whether it plugs in or unplugs; turn single times or the
  whole schedule on and off. Times are in your Home Assistant time zone. A
  time missed while the add-on was stopped isn't run later. Unplugging
  during a session ends the session.
- **Auto re-plug:** Octopus sometimes doesn't start a session after you plug
  in. When Plugged In has been on for `replug_after_min` minutes (default 10)
  with no session and the add-on is connected, it unplugs, waits 30 seconds
  and plugs back in, up to `replug_attempts` times (default 3). It then gives
  up until the car is next unplugged or a session starts, and the wait starts
  again after each re-plug. Changing the minutes or tries on the Automation
  tab is kept until you change the add-on options themselves.

Settings are saved in `/data/automation.json`.

## How it works

1. The add-on connects to your provider's OCPP server via WebSocket
2. It registers as a chargepoint (BootNotification)
3. It sends periodic heartbeats and meter values
4. When you "plug in" via the companion integration, it reports `Preparing`
5. Your provider creates a charge schedule and sends `RemoteStartTransaction`
6. The proxy sends `StartTransaction`, reports `Charging`, and sends meter
   values while the simulated car ramps up to full power
7. When the provider ends the session, it sends `RemoteStopTransaction`
8. The proxy reports `Finishing`, sends `StopTransaction`, then returns to
   `Preparing`

If the connection drops, the add-on reconnects automatically, retrying with
increasing delays.

### While offline

Like a real charger, a dropped connection doesn't stop the session. Charging,
the energy register and any charging profile carry on, and the transaction
stays open. StartTransaction, StopTransaction and the session's MeterValues are
held in order and sent once the server accepts the BootNotification on
reconnect. Status updates and heartbeats aren't held; the current status is
sent after reconnecting instead. Held messages are saved to
`/data/offline_queue.json`, so they also survive an add-on restart. Up to
1,000 messages are held, and the oldest meter readings are dropped first.

If the add-on is stopped without warning mid-charge (power cut, crash), the
open transaction is closed on the next start. A StopTransaction with reason
`PowerLoss` is sent, using the last meter reading saved before the
interruption.

### StopTransaction readings

StopTransaction can include `transactionData` with the session's readings.
Two configuration keys choose what's included. Both are empty by default, as
on a Wallbox Pulsar Plus, so nothing is added unless your provider sets them
with ChangeConfiguration:

| Key | Default | Readings |
|-----|---------|----------|
| `StopTxnSampledData` | *(empty)* | At the start, every `MeterValueSampleInterval`, and at the stop |
| `StopTxnAlignedData` | *(empty)* | On each `ClockAlignedDataInterval` boundary |

Long sessions are thinned to at most 100 readings, and the first and last are
always kept.

## Companion Integration

Install the companion integration via HACS for the charger's Power, Energy
(Energy dashboard) and Current sensors and the Plugged In switch:

1. Add this repository to HACS as a custom repository (Integration category)
2. Install "OCPP Charge Proxy" from HACS
3. Restart Home Assistant
4. The integration should auto-discover the add-on. If not, go to
   Settings > Devices & Services > Add Integration > OCPP Charge Proxy

### Entities provided

| Entity | Type | Description |
|--------|------|-------------|
| Plugged In | Switch | Simulate car plugged in/unplugged |
| Power | Sensor | Current power draw (kW) |
| Energy | Sensor | Cumulative energy (kWh, works with energy dashboard) |
| Current | Sensor | Current draw (A) |

Everything else is on the add-on's web page. Your power, SoC and car plugged
in sensors and auto plug-in are set up on its **Simulation** tab (settings
from an older integration are moved there automatically); the add-on reads
those sensors itself through Home Assistant's API.

## Web GUI

Open the add-on from the sidebar (or **Open Web UI**). It updates live and
follows your Home Assistant theme.

- **Overview:** state, power, current, SoC and energy; controls for Plugged
  In, max current, a power override and a test SoC; the current session;
  and a chart of power, current (with your max and the provider limit) or
  SoC over the last 30 minutes to 6 hours.
- **Sessions:** the last 20 charging sessions (energy, duration, peak
  power, what ended them), kept across restarts.
- **Messages:** the last 300 OCPP messages both ways, with a filter, full
  JSON on click and a Copy button for sharing.
- **Provider:** what your provider has set: charging limits, charging
  profiles drawn as a timeline, the local authorisation list and every
  configuration key.
- **Simulation:** your power, SoC and car plugged in sensors and auto
  plug-in, with their live values (power source, reporting SoC, monitored
  SoC).
- **Automation:** the plug-in schedule and auto re-plug (see below).
- **Health:** version, uptime, reconnects and the last drop's reason,
  heartbeat and clock offset, whether the HA integration's push updates are
  connected, and any held messages.

## Getting your OCPP credentials

Your provider will supply three values needed to connect:

- **Server hostname** — the OCPP WebSocket endpoint
- **Chargepoint ID** — your unique chargepoint identifier
- **Password** — authentication password

You may also need to set `charger_model` and `charger_vendor` to match a
charger model your provider supports. The defaults work for providers that
accept Wallbox chargepoints.

Check your provider's app or documentation for how to obtain these credentials.
