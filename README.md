# OCPP Charge Proxy

[![License][license-shield]](LICENSE.md)
[![HACS][hacs-shield]][hacs-url]

![Supports aarch64 Architecture][aarch64-shield]
![Supports amd64 Architecture][amd64-shield]

Acts as a virtual OCPP 1.6 chargepoint that connects to smart tariff
providers on your behalf. Use it to get cheap-rate charging schedules
without a compatible charger, or to keep control of your charging
alongside provider-managed scheduling.

## Why?

When a charger is enrolled with a smart tariff provider via OCPP, the provider
takes exclusive control of charging sessions. That means solar diversion no
longer works — your home can be exporting surplus solar while the car sits idle,
waiting for the provider to schedule a cheap-rate slot.

This proxy solves the problem by presenting a virtual charger to your provider.
The provider sends its charging schedules to the proxy instead of your real
charger, and the proxy exposes the schedule as Home Assistant entities.
You then build automations that combine the provider schedule with solar
diversion, surplus export, or any other logic you choose — keeping the best
of both worlds.

## About

This Home Assistant add-on connects to any OCPP 1.6J compatible server as a
virtual chargepoint. When the server sends charge scheduling commands, the
proxy updates its state in Home Assistant so you can trigger automations to
control any charger, smart plug, or home battery.

Should work with any OCPP 1.6J provider that accepts chargepoint connections.
It's developed and tested against Octopus Energy, presenting itself as a
Wallbox Pulsar Plus.

It consists of two components:

- **Add-on** — runs the OCPP client (Docker container managed by HA Supervisor)
- **Integration** (HACS) — exposes entities for automations, dashboards, and the energy dashboard

Both are installed from this repository.

## Features

### Behaves like a real charger

- **Realistic charging start.** After `StartTransaction` the simulated car
  waits a few seconds before drawing current, then ramps up to full power
  (`start_delay_s`, default 3s, and `ramp_up_s`, default 5s), instead of
  jumping straight to full power.
- **Charging taper near full.** With a SoC sensor for reporting set, power
  stays at full up to 90% SoC, then tapers to 30% of full power at 100%, like
  a real car's charge curve.
- **Accurate energy meter.** The energy register counts exactly what was
  delivered, including the start delay, ramp-up and taper, and carries over
  across restarts (so the Energy dashboard never sees a spike or a reset).
- **Car full.** With a SoC sensor set, at 100% the charger reports
  `SuspendedEV` and stops drawing power, like a real car with a full battery.
  The session stays open: ending it is up to your provider. If the SoC drops
  below 100%, charging resumes.
- **You set the maximum current.** The **Current Amps Setting** in Home
  Assistant is the charger's maximum, like a real Wallbox's max-current
  setting. Your provider can lower the current below it, but not raise it
  above it. The setting is remembered across restarts.
- **Charging profiles.** Your provider's charging profiles pause
  (`SuspendedEVSE`) and resume charging as scheduled.

### Reliable

- **Keeps charging while offline.** If the connection to your provider drops
  mid-charge, charging carries on and the session stays open.
  StartTransaction, StopTransaction and the session's meter readings are held
  in order and sent as soon as it reconnects. Held messages survive an add-on
  restart.
- **Recovers from power cuts.** If the add-on stops without warning
  mid-charge (power cut, crash), the open session is closed on the next start
  with a StopTransaction (reason `PowerLoss`), using the last saved meter
  reading, as a real charger does.
- **Crash-safe storage.** Everything the add-on stores (energy register,
  held messages, open session, current setting) is written atomically, with a
  backup copy, so a power cut mid-write can't reset your meter to 0.
- **Fast recovery.** After an add-on restart, Home Assistant reconnects
  within a few seconds and re-sends the power and SoC sensor values.

### Works with your car in Home Assistant

- **Power sensor (optional).** Report real power (e.g. from a smart plug or
  your actual charger) to your provider instead of the simulation.
- **SoC sensor for reporting (optional).** Report your car's state of charge
  to your provider, and enable car full and the charging taper.
- **Car plugged in sensor (optional).** Pick a binary sensor, such as your
  car's "charging cable connected", and **Plugged In** switches on
  automatically when it turns on. It never unplugs; that stays up to you.
- **Auto plug-in (optional).** Switch Plugged In on when the SoC drops
  below a threshold you choose (default 30%), so your provider can schedule a
  charge. It can watch a different SoC sensor from the one reported to your
  provider (e.g. for a car that may be away from home), and only triggers
  once per drop, so unplugging by hand doesn't get undone.
- **Push updates.** The add-on pushes its state to Home Assistant as it
  changes, so entities update within about a second (live power every 10s).

### Diagnostics

- **Last Command Received / Sent** sensors with a readable summary, status,
  response time and the last 10 commands each way.
- **Last Heartbeat** sensor: when your provider last answered, the round
  trip time and how far its clock is from yours.
- **Power Source**, **Reporting SoC** and **Monitored SoC** sensors showing
  where each value comes from, and the SoC values in use.
- A **status page** in the Home Assistant sidebar (the add-on's Web UI):
  connection, state, power, energy, current, SoC, transaction, held messages,
  last heartbeat and last commands.
- **Quieter logs.** OCPP messages are logged at `info`, except Heartbeats
  (every 10s with Octopus) and periodic meter readings (every 60s), which only
  show at `debug`. Clock-aligned readings (every 15 min) stay at `info`.

## Step 1: Install the Add-on

1. Add this repository to your Home Assistant add-on store:

   [![Add repository][repository-badge]][repository-url]

   Or manually: **Settings > Add-ons > Add-on Store > ... > Repositories** and
   add this repository URL.

2. Install the **OCPP Charge Proxy** add-on
3. Configure your OCPP credentials (server hostname, chargepoint ID, password)
4. Start the add-on

See the [add-on documentation][docs] for all add-on options, including the
start delay and ramp-up, the starting current, and seeding the energy
register when migrating from a real charger.

## Step 2: Install the Integration (HACS)

The integration creates HA entities and auto-discovers the add-on.

1. Add this repository to HACS as a **custom repository** (category: Integration):

   [![Add to HACS][hacs-badge]][hacs-add-url]

   Or manually: **HACS > Integrations > ... > Custom repositories** and add
   this repository URL.

2. Install **OCPP Charge Proxy** from HACS
3. Restart Home Assistant
4. The integration should auto-discover the add-on. If not, go to
   **Settings > Devices & Services > Add Integration** and search for
   "OCPP Charge Proxy"
5. Optionally set up the sensors below in the integration's settings
   (**Configure**)

### Integration options

All options are optional. Clear a field to stop using that sensor.

| Option | What it does |
|--------|--------------|
| **Power sensor** | A sensor reporting power in watts. Its value is reported to your provider instead of the simulated power (capped at what the charger could deliver at its current setting). |
| **SoC sensor for reporting** | A sensor reporting the car's charge in %. Sent to your provider in meter values while a car is plugged in, and enables car full and the charging taper. |
| **Car plugged in sensor** | A binary sensor (e.g. your car's "charging cable connected"). When it changes from off to on, Plugged In is switched on. It never switches Plugged In off, so unplug with the switch or an automation as usual. Unavailable/unknown readings in between are ignored, and it doesn't plug in on the first reading after a restart. The switch stays usable by hand, and it works alongside auto plug-in. |
| **Plug in automatically when the SoC drops low** | Switches Plugged In on once when the watched SoC drops below the threshold. Re-arms once the SoC is back at or above it. Doesn't trigger on the first reading after a restart, or if already plugged in. |
| **SoC sensor to watch for auto plug-in** | Watch this sensor for auto plug-in instead of the reporting SoC sensor above. It's never reported to your provider. |
| **Plug in below this SoC** | The auto plug-in threshold (1–99%, default 30%). |

### Entities provided

| Entity | Type | Description |
|--------|------|-------------|
| Plugged In | Switch | Simulate car plugged in/unplugged |
| Current Amps Setting | Select | Charger's maximum current (6–32A), remembered across restarts. Your provider can lower the current below it but not raise it; attributes `effective_amps` and `provider_limit_amps` show what's in use |
| OCPP Charge Proxy State | Sensor | OCPP state: `Available`, `Preparing`, `Charging`, `SuspendedEV`, `SuspendedEVSE`, `Finishing`, `Unavailable` |
| Power | Sensor | Live power draw (kW) |
| Energy | Sensor | Cumulative energy (kWh, Energy dashboard compatible) |
| Current | Sensor | Current draw (A) |
| Connected to Server | Binary Sensor | Connected to your provider's OCPP server |
| Power Source | Sensor (diagnostic) | `entity` (your power sensor is in use) or `simulated` |
| Reporting SoC | Sensor (diagnostic) | The SoC being reported to your provider (e.g. `64%`), `no reading` (sensor set but no value, nothing sent) or `not set` (no SoC reported, car full off). Attribute `soc_percent` has the number |
| Monitored SoC | Sensor (diagnostic) | The SoC auto plug-in watches (e.g. `64%`), `no reading` or `not set`. Attributes: `soc_percent`, `entity_id`, `source`, `auto_plug`, `threshold`, `armed` |
| Last Heartbeat | Sensor (diagnostic) | When your provider last answered a Heartbeat. Attributes: `round_trip_ms`, `interval_s`, `server_time`, `clock_offset_s` |
| Last Command Received | Sensor (diagnostic) | Last OCPP command from your provider (e.g. `RemoteStartTransaction`). Attributes: `timestamp`, `summary`, `status`, `round_trip_ms`, `message_id`, `payload`, `response`, `recent` (last 10) |
| Last Command Sent | Sensor (diagnostic) | Last message sent to your provider, excluding Heartbeat and MeterValues. Same attributes, with your provider's response |

## Usage

1. Start the add-on and verify it connects (check the add-on log or its
   status page in the sidebar)
2. Turn on **Plugged In** to simulate connecting a car (or let the car
   connected sensor or auto plug-in do it)
3. Set a departure time and charge amount in your provider's app
4. Your provider will schedule charging and send start/stop commands
5. Create automations based on the **OCPP Charge Proxy State** sensor to
   control your actual charger, for example:

```yaml
automation:
  - alias: "Charge when the provider schedules it"
    triggers:
      - trigger: state
        entity_id: sensor.ocpp_charge_proxy_state
    actions:
      - action: >-
          {{ 'switch.turn_on' if trigger.to_state.state == 'Charging'
             else 'switch.turn_off' }}
        target:
          entity_id: switch.ev_charger_plug
```

### What a charging session looks like

1. **Plugged In** turns on: the proxy reports `Preparing`
2. Your provider sends `RemoteStartTransaction` (often with a charging
   profile): the proxy sends `StartTransaction`, then reports `Charging`
3. The simulated car waits a few seconds, then ramps up to full power. Meter
   readings go to your provider every `MeterValueSampleInterval` (60s with
   Octopus), plus clock-aligned readings if it asks for them
4. If the profile pauses charging, the proxy reports `SuspendedEVSE` until it
   resumes. If the car reaches 100% (with a SoC sensor), it reports
   `SuspendedEV`
5. The session ends when your provider sends `RemoteStopTransaction` or you
   unplug: the proxy reports `Finishing`, sends `StopTransaction` (with the
   reason, e.g. `Remote` or `EVDisconnected`), then returns to `Preparing`
   (or `Available` if unplugged)

## Development

Tests run in CI on every push. To run them locally:

```bash
# Add-on (from the ocpp_charge_proxy folder)
cd ocpp_charge_proxy
pip install -r requirements.txt pytest pytest-asyncio pytest-aiohttp
python -m pytest tests/ -v

# Integration, against a real Home Assistant core (from the repository root)
pip install pytest-homeassistant-custom-component
python -m pytest tests/ -v -o asyncio_mode=auto
```

## Documentation

See the [add-on documentation][docs] for full configuration details, including
all add-on options, how the proxy behaves while offline, StopTransaction
readings, charger migration and getting your OCPP credentials. The
[changelog][changelog] lists what changed in each version.

[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg
[license-shield]: https://img.shields.io/badge/license-MIT-blue.svg
[hacs-shield]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[hacs-url]: https://github.com/hacs/integration
[hacs-badge]: https://my.home-assistant.io/badges/hacs_repository.svg
[hacs-add-url]: https://my.home-assistant.io/redirect/hacs_repository/?owner=thewhale21&repository=ocpp_charge_proxy&category=integration
[docs]: ocpp_charge_proxy/DOCS.md
[repository-badge]: https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg
[repository-url]: https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fthewhale21%2Focpp_charge_proxy
[changelog]: ocpp_charge_proxy/CHANGELOG.md
