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
| `current_amps` | `32` | Maximum charging current in amps (6/10/13/16/20/25/32). Starting value: once you change the current in Home Assistant that's remembered, until you change this option again |
| `initial_energy_wh` | `0` | Seed the energy register (Wh). Set to your old charger's meter reading when migrating. Only applied if higher than the stored register (the meter never goes backwards); cleared after first boot. |
| `start_delay_s` | `3` | Seconds after StartTransaction before the simulated car draws any current (also applied when resuming after a charging-profile pause). `0` = instant. |
| `ramp_up_s` | `5` | Seconds for power to ramp linearly from 0 to full after the start delay. `0` = jump straight to full power. Not applied when power comes from a real power entity. |
| `log_level` | `info` | Logging level (debug/info/warning/error). OCPP messages are logged at `info`, except Heartbeats and idle periodic meter readings, which only show at `debug` (clock-aligned readings and readings during a session stay at `info`) |

### Controlling your charger

Use the companion integration's **OCPP Charge Proxy State** sensor to trigger automations when
your provider starts or stops charging. For example, create an automation that
turns on a smart plug when the state changes to `Charging` and turns it off
when it changes to `Preparing` or `Available`.

### Power entity

You can optionally configure a Home Assistant power sensor in the companion
integration's settings. The proxy will report this real power value to your
provider instead of simulating power delivery. The value is capped at what the
virtual chargepoint could physically deliver at its current setting.

If not configured, the proxy uses a realistic power simulation.

### Car battery (SoC) entity

You can also set a **car battery (SoC) sensor**, for example from your car's
own integration, reporting 0–100%. When set:

- The car's state of charge is sent to your provider whenever it asks for
  `SoC` in its meter values (Octopus does), while a car is plugged in.
- **Car full:** when the sensor reads 100% during a session, the charger
  reports `SuspendedEV` and stops drawing power, as a real car does when its
  battery is full. The session stays open; if the SoC drops below 100%,
  charging resumes. A charging-profile pause (`SuspendedEVSE`) takes priority.

Leave it unset (or clear it) and no SoC is reported and car-full never
triggers. If the sensor becomes unavailable, SoC reporting pauses until it
comes back.

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
| Current Amps Setting | Select | Charger's maximum current (6-32A), remembered across restarts. Your provider can lower the current below it but not raise it; attributes `effective_amps` and `provider_limit_amps` show what's in use |
| OCPP Charge Proxy State | Sensor | OCPP state (Available/Preparing/Charging/etc.) |
| Power | Sensor | Current power draw (kW) |
| Energy | Sensor | Cumulative energy (kWh, works with energy dashboard) |
| Current | Sensor | Current draw (A) |
| Power Source | Sensor (diagnostic) | Whether using real entity or simulated values |
| SoC Source | Sensor (diagnostic) | `entity` (reporting your car battery sensor), `no reading` (sensor set but no value, nothing sent) or `not set` (no SoC reported, car full off) |
| Connected to Server | Binary Sensor | Connected to OCPP server |
| Last Command Received | Sensor (diagnostic) | Last OCPP command from your provider (e.g. `RemoteStartTransaction`). Attributes: `timestamp`, `summary`, `status`, `round_trip_ms`, `message_id`, `payload`, `response`, `recent` (last 10) |
| Last Command Sent | Sensor (diagnostic) | Last message sent to your provider, excluding Heartbeat and MeterValues. Same attributes, with the server's response |
| Monitored SoC | Sensor (diagnostic) | SoC (%) that auto plug-in watches. Attributes: `entity_id`, `source`, `auto_plug`, `threshold`, `armed` |
| Last Heartbeat | Sensor (diagnostic) | When your provider last answered a Heartbeat. Attributes: `round_trip_ms`, `interval_s`, `server_time`, `clock_offset_s` |

### Integration options

In the integration's settings (Configure), you can optionally set:

- a **power sensor**, reporting power in watts (W), such as your battery
  charge power or grid demand sensor;
- a **car battery (SoC) sensor**, reporting the car's charge in %.

Clear a field to stop using that sensor.

You can also turn on **Plug in automatically when the car's SoC drops low**
and choose the threshold (default 30%). When the SoC drops below it, Plugged
In is switched on so your provider can schedule a charge. It triggers once
per drop: unplugging by hand while the SoC is still low won't plug it back
in, and it re-arms once the SoC is back above the threshold.

If your car has a "charging cable connected" (or similar) binary sensor, you
can set it as the **car connected sensor**: when it changes from off to on,
Plugged In is switched on. It never switches Plugged In off, so unplug with
the switch or an automation as usual. Unavailable/unknown readings in between
are ignored, and it doesn't plug in on the first reading after a restart. The
switch stays usable by hand, and it works alongside auto plug-in.

With a car battery (SoC) sensor set, the simulated power also **tapers** above
90% SoC, down to 30% of full power at 100%, as a real car's does.

By default auto plug-in watches the car battery (SoC) sensor above. You can pick a
different **SoC sensor to watch for auto plug-in** instead. That sensor is
only watched, never reported to your provider, which is useful if the car
may be away from home: you can watch its SoC without it being sent as the
charging car's state of charge (leave the reported SoC sensor empty to send
none at all).

The add-on pushes its state to the integration as it changes, so entities
update within a second or so (live power every 10s). Changes to the power and
SoC sensors are sent to the add-on straight away. If push updates aren't
available (e.g. an older add-on) the integration polls every 10 seconds
instead.

The add-on's own page (sidebar) shows the connection, state, power, energy,
car SoC, the current transaction, any held messages and the last command
received from and sent to your provider.

## Getting your OCPP credentials

Your provider will supply three values needed to connect:

- **Server hostname** — the OCPP WebSocket endpoint
- **Chargepoint ID** — your unique chargepoint identifier
- **Password** — authentication password

You may also need to set `charger_model` and `charger_vendor` to match a
charger model your provider supports. The defaults work for providers that
accept Wallbox chargepoints.

Check your provider's app or documentation for how to obtain these credentials.
