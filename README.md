# OCPP Charge Proxy

[![License][license-shield]](LICENSE.md)

![Supports aarch64 Architecture][aarch64-shield]
![Supports amd64 Architecture][amd64-shield]

Acts as a virtual OCPP 1.6 chargepoint that connects to smart tariff
suppliers on your behalf. Use it to get cheap-rate charging schedules
without a compatible charger, or to keep control of your charging
alongside supplier-managed scheduling.

## Why?

When a charger is enrolled with a smart tariff supplier via OCPP, the supplier
takes exclusive control of charging sessions. That means solar diversion no
longer works — your home can be exporting surplus solar while the car sits idle,
waiting for the supplier to schedule a cheap-rate slot.

This proxy solves the problem by presenting a virtual charger to your supplier.
The supplier sends its charging schedules to the proxy instead of your real
charger, and the proxy exposes the schedule as Home Assistant entities.
You then build automations that combine the supplier schedule with solar
diversion, surplus export, or any other logic you choose — keeping the best
of both worlds.

## About

This Home Assistant add-on connects to any OCPP 1.6J compatible server as a
virtual chargepoint. When the server sends charge scheduling commands, the
proxy updates its state in Home Assistant so you can trigger automations to
control any charger, smart plug, or home battery.

Should work with any OCPP 1.6J supplier that accepts chargepoint connections.
It's developed and tested against Octopus Energy, presenting itself as a
Wallbox Pulsar Plus.

It's a single add-on: it runs the OCPP client, has its own web page in the
Home Assistant sidebar, and creates its own Home Assistant entities (Plugged
In, Power, Energy and Current). No integration or HACS needed.

## Features

### Behaves like a real charger

- **Realistic charging start.** After `StartTransaction` the simulated car
  waits a few seconds before drawing current, then ramps up to full power
  (start delay, default 3s, and ramp-up, default 5s, set on the Settings
  tab), instead of jumping straight to full power.
- **Charging taper near full.** With a SoC sensor for reporting set, power
  stays at full up to 90% SoC, then tapers to 30% of full power at 100%, like
  a real car's charge curve.
- **Accurate energy meter.** The energy register counts exactly what was
  delivered, including the start delay, ramp-up and taper, and carries over
  across restarts (so the Energy dashboard never sees a spike or a reset).
- **Car full.** With a SoC sensor set, at 100% the charger reports
  `SuspendedEV` and stops drawing power, like a real car with a full battery.
  The session stays open: ending it is up to your supplier. If the SoC drops
  below 100%, charging resumes.
- **You set the maximum current.** The **Max current** on the add-on's web
  page is the charger's maximum, like a real Wallbox's max-current
  setting. Your supplier can lower the current below it, but not raise it
  above it. The setting is remembered across restarts.
- **Charging profiles.** Your supplier's charging profiles pause
  (`SuspendedEVSE`) and resume charging as scheduled.

### Reliable

- **Keeps charging while offline.** If the connection to your supplier drops
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
  Plugged In is remembered, so a car left plugged in comes back as
  `Preparing`, ready for your supplier to start a new session.

### Works with your car in Home Assistant

Set these up on the add-on's **Settings** tab. The add-on follows your
sensors live through Home Assistant's API.

- **Power sensor (optional).** Report real power (e.g. from a smart plug or
  your actual charger) to your supplier instead of the simulation.
- **SoC sensor for reporting (optional).** Report your car's state of charge
  to your supplier, and enable car full and the charging taper.
- **Car plugged in sensor (optional).** Pick a binary sensor, such as your
  car's "charging cable connected", and **Plugged In** switches on
  automatically when it turns on. It never unplugs; that stays up to you.
- **Auto plug-in (optional).** Switch Plugged In on when the SoC drops
  below a threshold you choose (default 30%), so your supplier can schedule a
  charge. It can watch a different SoC sensor from the one reported to your
  supplier (e.g. for a car that may be away from home), and only triggers
  once per drop, so unplugging by hand doesn't get undone.
- **Home Assistant entities, no integration needed.** The add-on creates a
  **Plugged In** helper (`input_boolean.ocpp_charge_proxy_plugged_in`): turn
  it on or off to plug in or unplug, and it follows the add-on's own Plugged
  In. It also keeps **Power**, **Energy** (for the Energy dashboard) and
  **Current** sensors up to date. The sensors show as unavailable while the
  add-on is stopped.
- **Plug-in schedule.** Switch Plugged In on or off at set times and days,
  as many times a day as you like, from the add-on's web page (Automation
  tab).
- **Auto re-plug.** If your supplier hasn't started a session 10 minutes
  after plugging in, the add-on unplugs for 30 seconds and plugs back in, up
  to 3 times. On/off, minutes and tries are on the Schedule tab.

### Diagnostics

- A **web GUI** in the Home Assistant sidebar (the add-on's Web UI), live
  over push updates and styled to match your HA theme, light or dark:
  - **Header:** a health dot left of the title, green when healthy and amber/red
    when not (hover for the issues), linking to Diagnostics › Health.
  - **Overview:** state, power, current, SoC and energy; the current
    session; your supplier's planned smart charging slots (found
    automatically from the Octopus Energy, EDF Energy or E.ON Next integration); and a chart (shaded by state, with session start/end marked)
    of power, current (with your max and the supplier limit) or SoC over
    the last 30 minutes to 24 hours, or 14 days, read from Home Assistant's
    history of the add-on's sensors. Drag or scroll on it to zoom.
  - **Sessions:** energy per day for the last 14 days (click a day to show
    its sessions); the last 20 charging sessions (energy, duration, peak
    power, what ended them, with details, IDs and the power curve on click),
    and plug-ins that never got a session with the reason, kept across
    restarts.
  - **Schedule:** the plug-in schedule (below), with one-off times and a
    view of the next 7 days where you click or drag to add a slot and click
    one to change, delete or skip it;
    auto plug-in and auto re-plug.
  - **Settings:** Charge now; controls for Plugged In, max current and
    continuing a session after a restart; the
    simulated car's start delay and ramp-up; and your power, SoC and car
    plugged in sensors, with live values.
  - **Diagnostics:** **Health** (version, uptime, reconnects and the last
    drop's reason, heartbeat and clock offset, the Home Assistant link and
    the add-on's entities, held messages, and at the bottom what your
    supplier has set: charging limits, charging profiles as a timeline, the
    local authorisation list and every configuration key) and **Messages**
    (the last 300 OCPP messages both ways, with a filter, full JSON on click
    and Copy), and **Debug** (test values, send a message, drop the
    connection or restart, override the 6-hour scheduling guard, logs and
    log level, a diagnostics bundle to download, and clearing the session
    history or message log).
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
starting current and seeding the energy register when migrating from a real
charger. Everything else is set on the add-on's web page (Settings tab).

## Step 2: Pick your sensors (optional)

On the add-on's web page (sidebar), open the **Settings** tab to pick your
power, SoC and car plugged in sensors and set up auto plug-in.

### Upgrading from 1.x (with the integration)

1. Remove the integration: **Settings > Devices & services > OCPP Charge
   Proxy > Delete**, then remove it from HACS
2. Restart the add-on. It creates its own entities. `sensor.ocpp_charge_proxy_energy`
   keeps the same entity ID, so its Energy dashboard history carries on
3. Pick your sensors again on the **Settings** tab
4. Update automations that used `switch.ocpp_charge_proxy_plugged_in` to use
   `input_boolean.ocpp_charge_proxy_plugged_in`. The charger state and other
   details are now on the add-on's web page

Until the integration is removed, the add-on leaves the sensors alone (its
Health tab says so).

### Sensor and auto plug-in options

Sensors are on the **Settings** tab, auto plug-in on the **Schedule** tab.

All optional. Choose "None" to stop using a sensor.

| Option | What it does |
|--------|--------------|
| **Power sensor** | A sensor reporting power in W or kW. Its value is reported to your supplier instead of the simulated power (capped at what the charger could deliver at its current setting). |
| **SoC sensor** | A sensor reporting the car's charge in %. Sent to your supplier in meter values while a car is plugged in, and enables car full and the charging taper. |
| **Car plugged in sensor** | A binary sensor (e.g. your car's "charging cable connected"). When it changes from off to on, Plugged In is switched on. It never switches Plugged In off, so unplug with the switch or an automation as usual. Unavailable/unknown readings in between are ignored, and it doesn't plug in on the first reading after a restart. |
| **Auto plug-in** | Switches Plugged In on once when the watched SoC drops below the threshold (1–99%, default 30%). Re-arms once the SoC is back at or above it. Doesn't trigger on the first reading after a restart, or if already plugged in. |
| **SoC sensor to watch** | Watch this sensor for auto plug-in instead of the reporting SoC sensor. It's never reported to your supplier. |

### Entities provided

The add-on creates these in Home Assistant:

| Entity | Type | Description |
|--------|------|-------------|
| `input_boolean.ocpp_charge_proxy_plugged_in` | Helper (toggle) | Plugged In: turn on/off to plug in or unplug. Kept in step with the add-on |
| `sensor.ocpp_charge_proxy_power` | Sensor | Live power draw (kW) |
| `sensor.ocpp_charge_proxy_energy` | Sensor | Cumulative energy (kWh, Energy dashboard compatible) |
| `sensor.ocpp_charge_proxy_current` | Sensor | Current draw (A) |
| `sensor.ocpp_charge_proxy_status` | Sensor | OCPP state (Available, Preparing, Charging...) |
| `sensor.ocpp_charge_proxy_current_limit` | Sensor | Current the charger uses (A), with your max and the supplier's limit as attributes |

The sensors are updated by the add-on rather than an integration, so they
can't be renamed in the UI and aren't grouped under a device, and they show as
unavailable while the add-on is stopped. The Plugged In helper is a normal
helper you can rename. If the add-on is stopped, toggling it does nothing and
it's set back when the add-on starts. The charger state, OCPP connection,
heartbeat, commands and sensor details are on the add-on's web page.

## Usage

1. Start the add-on and verify it connects (its web page in the sidebar
   shows the charger state and the OCPP connection)
2. Turn on **Plugged In** (the helper, or on the add-on's web page) to
   simulate connecting a car (or let the car
   connected sensor or auto plug-in do it)
3. Set a departure time and charge amount in your supplier's app
4. Your supplier will schedule charging and send start/stop commands
5. Create automations based on the **Power** sensor to control your actual
   charger: with the simulated power, it's above 0 while your supplier has
   the charger charging. For example:

```yaml
automation:
  - alias: "Charge when the supplier schedules it"
    triggers:
      - trigger: numeric_state
        entity_id: sensor.ocpp_charge_proxy_power
        above: 0
        id: "on"
      - trigger: numeric_state
        entity_id: sensor.ocpp_charge_proxy_power
        below: 0.01
        id: "off"
    actions:
      - action: "switch.turn_{{ trigger.id }}"
        target:
          entity_id: switch.ev_charger_plug
```

### What a charging session looks like

1. **Plugged In** turns on: the proxy reports `Preparing`
2. Your supplier sends `RemoteStartTransaction` (often with a charging
   profile): the proxy sends `StartTransaction`, then reports `Charging`
3. The simulated car waits a few seconds, then ramps up to full power. Meter
   readings go to your supplier every `MeterValueSampleInterval` (60s with
   Octopus), plus clock-aligned readings if it asks for them
4. If the profile pauses charging, the proxy reports `SuspendedEVSE` until it
   resumes. If the car reaches 100% (with a SoC sensor), it reports
   `SuspendedEV`
5. The session ends when your supplier sends `RemoteStopTransaction` or you
   unplug: the proxy reports `Finishing`, sends `StopTransaction` (with the
   reason, e.g. `Remote` or `EVDisconnected`), then returns to `Preparing`
   (or `Available` if unplugged)

## Development

Tests run in CI on every push. To run them locally:

```bash
cd ocpp_charge_proxy
pip install -r requirements.txt pytest pytest-asyncio pytest-aiohttp
python -m pytest tests/ -v

```

## Documentation

See the [add-on documentation][docs] for full configuration details, including
all add-on options, how the proxy behaves while offline, StopTransaction
readings, charger migration and getting your OCPP credentials. The
[changelog][changelog] lists what changed in each version.

[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg
[license-shield]: https://img.shields.io/badge/license-MIT-blue.svg
[docs]: ocpp_charge_proxy/DOCS.md
[repository-badge]: https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg
[repository-url]: https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fthewhale21%2Focpp_charge_proxy
[changelog]: ocpp_charge_proxy/CHANGELOG.md
