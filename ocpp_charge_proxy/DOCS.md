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
| `continue_session_on_restart` | `true` | Carry a charging session on across an add-on restart (e.g. an update) instead of ending it; see [While offline](#while-offline) |
| `log_level` | `info` | Logging level (debug/info/warning/error). OCPP messages are logged at `info`, except Heartbeats and periodic meter readings (in a session or not), which only show at `debug`. Clock-aligned readings stay at `info` during a session (outside one, they're `debug` too) |

### Controlling your charger

Use the **Power** sensor (`sensor.ocpp_charge_proxy_power`) to trigger automations when
your provider starts or stops charging: with the simulated power, it's above
0 while the charger is charging. For example, turn on a smart plug when it
rises above 0 and off when it drops back to 0.

### Power entity

You can optionally pick a Home Assistant power sensor (W or kW) on the
add-on's **Settings** tab. The proxy will report this real power value to your
provider instead of simulating power delivery. The value is capped at what the
virtual chargepoint could physically deliver at its current setting.

If not configured, the proxy uses a realistic power simulation.

### SoC sensor for reporting

You can also pick a **SoC sensor** on the Settings tab, for example from
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

### Auto plug-in

**Auto plug-in** (Schedule tab) switches Plugged In on once when the SoC
drops below the level you set. With **Automatically adjust schedule to fit
auto plug-in** on, it also adds the charge to the schedule as a one-off,
for the hours you choose (**Charge for**, 0.5 to 12):

- The slot runs from plugging in to the first ready time your supplier
  accepts at least that long away (rounded up to the half hour; with EDF,
  the next time between 04:00 and 11:00). It unplugs then, after the
  supplier stops the session or the unplug wait (60 s by default).
- Octopus Energy, with Force schedule on supplier on: if that puts more
  than 6 hours in 24, the next scheduled slot starts that many hours later
  (or is skipped, if nothing is left). With it off there's no 6-hour limit,
  for auto plug-in or the schedule.
- If it meets or overlaps the next scheduled slot, they become one slot,
  ending at the schedule's unplug.
- The supplier's ready time is set to the end of the slot (E.ON Next has
  none to set).

The entries show on the Schedule tab as "Auto plug-in, once on", and run
even with the schedule off.

### Schedule, auto re-plug and start-up

- **Schedule** (**Schedule** tab): the next 7 days are shown as slots,
  each running from a plug-in to its unplug. Click or drag across a day to
  add a slot; click a slot to change its times, the days it repeats on
  (**Every week**) or its date (**Once**), turn it off, delete it, or skip
  it once (its plug-in and unplug both don't run; it shows hatched, and
  **Undo skip** puts it back). Changes are saved straight away. An unplug
  time with no plug-in before it (e.g. "unplug at 07:00 every day", to
  unplug anything left plugged in) shows as a small tick, and can be
  changed or deleted the same way. Times are in your Home Assistant time
  zone. A time missed while the add-on was stopped isn't run later.
  Unplugging during a session ends the session.
- **One-off slots:** a **Once** slot runs on its date only. Once it has
  run it's kept for 14 days: sessions on the **Sessions** tab that ran in
  a one-off slot are tagged **One-off** (or **Auto plug-in** / **Charge
  now**). A skipped unplug isn't used for the ready time.
- **Starting inside a scheduled stretch:** if the add-on starts (or
  restarts) while the schedule has the car plugged in, e.g. at 02:00 with
  plug in 23:30 and unplug 07:00, and Plugged In is off, it plugs in
  straight away (and with Force schedule on supplier, sets the ready time
  once Home Assistant is connected). It never unplugs at start-up.
- **Force schedule on supplier** (**Schedule** tab, off by default):
  when the schedule plugs in, the add-on sets your supplier's smart
  charging ready-by time to the schedule's next unplug, for example plug in
  02:00 and unplug 04:00 sets 04:00; plug in 06:00 and unplug 08:00 sets
  08:00. Only at scheduled plug-ins. Ready times are in 30-minute steps:
  Octopus Energy accepts any time of day, EDF Energy 04:00 to 11:00. While
  it's on, unplug times in the schedule are limited to those (the slot
  editor only offers those). E.ON Next's integration
  has no ready time setting. While it's on, the Next 7 days card outlines
  the schedule's slots in grey, and with Octopus Energy the schedule can't plug in for more than
  6 hours in any 24 (Octopus's daily smart charging cap): slots that go
  over are marked in red, and a change that goes over isn't saved. With the ready time off, there's no limit.
  At a scheduled unplug during a charging session, it waits for your
  supplier to stop the session itself (so it ends cleanly), then unplugs;
  if the supplier hasn't stopped it in time, it unplugs anyway. The wait
  is set under the switch (**Wait for the supplier at unplug**, 60 s by
  default, 0 to unplug straight away). The Overview shows "Unplugging by …"
  meanwhile.
  **Supplier's plan check**: while the schedule has the car plugged in,
  the add-on checks your supplier's planned slots up to the ready time it
  set against the schedule. With plug-ins 16:00–18:00 and 20:00–22:00, the
  first stretch is checked from 16:00 (slots up to 18:00) and the second
  from 20:00 (slots up to 22:00). It's flagged if a slot runs past the
  unplug, or if the supplier's ready time was changed (e.g. in its app)
  from the one the schedule set. The check starts 5 minutes after the
  plug-in, to give the supplier time to plan, and follows the plan as it
  changes. The result shows on the Overview's Smart charging card and the
  Schedule tab; a mismatch also as a red chip on the Overview, and in the
  log. The supplier's planned slots are outlined in its colour on the Next
  7 days card (whether or not this is on).
- **Auto re-plug** (**Schedule** tab): Octopus sometimes doesn't start a session after you plug
  in. When Plugged In has been on for the set minutes (default 10) with no
  session and the add-on is connected, it unplugs, waits 30 seconds and
  plugs back in, up to the set number of tries (default 3). It then gives up
  until the car is next unplugged or a session starts, and the wait starts
  again after each re-plug. If your supplier's smart charging plan is found
  (see the Overview tab), a planned slot counts too: it only re-plugs when
  nothing has been scheduled after the set minutes, not while it waits for
  a slot later on. A slot that's running now with no session is different:
  the status shows **Waiting for supplier** (amber) instead of Scheduled,
  and since Octopus may only start a session at the next half hour (e.g.
  after the add-on restarted mid-slot), the wait counts from the next :00
  or :30: with no session the set minutes after that, it re-plugs.
- **Start delay and ramp-up** (**Settings** tab, Simulated car): after
  StartTransaction (or resuming after a charging-profile pause) the simulated
  car waits the start delay (default 3s) before drawing current, then ramps
  linearly to full power over the ramp-up (default 5s). 0 and 0 = full power
  straight away. Not applied when power comes from your power sensor.

Settings are saved in `/data/automation.json`.

## How it works

1. The add-on connects to your provider's OCPP server via WebSocket
2. It registers as a chargepoint (BootNotification)
3. It sends periodic heartbeats and meter values
4. When you "plug in" (the Plugged In helper or the web page), it reports
   `Preparing`
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

When the add-on is restarted mid-charge (an update, a restart from Home
Assistant), it leaves the session open by default
(`continue_session_on_restart`): no StopTransaction or Unavailable, just
the connection closing, as when a charger loses its connection. When it's
back (within 10 minutes, with Plugged In still on) it reports Charging and
carries on with the same transaction, energy and charging profile.
Otherwise, or with the option off, the session is stopped with reason
`Reboot`, and your supplier starts a new one (Octopus at the next hour or
half hour). If the supplier sends a new RemoteStart instead of carrying on,
the old session is stopped (`Reboot`) and the new one started straight
away.

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

## Home Assistant entities

The add-on creates its own entities (no integration needed):

| Entity | Type | Description |
|--------|------|-------------|
| `input_boolean.ocpp_charge_proxy_plugged_in` | Helper (toggle) | Plugged In: turn on/off to plug in or unplug. Kept in step with the add-on's own Plugged In |
| `sensor.ocpp_charge_proxy_power` | Sensor | Current power draw (kW) |
| `sensor.ocpp_charge_proxy_energy` | Sensor | Cumulative energy (kWh, works with the Energy dashboard) |
| `sensor.ocpp_charge_proxy_current` | Sensor | Current draw (A) |
| `sensor.ocpp_charge_proxy_status` | Sensor | OCPP state (Available, Preparing, Charging...) |
| `sensor.ocpp_charge_proxy_current_limit` | Sensor | Current the charger uses (A), with your max and the provider's limit as attributes |

- The sensors are posted by the add-on, so they can't be renamed in the UI and
  aren't grouped under a device. They show as unavailable while the add-on is
  stopped, and come back when it (or Home Assistant) restarts.
- The Plugged In helper is a normal helper. While the add-on is stopped,
  toggling it does nothing, and it's set back to the add-on's value when the
  add-on starts.
- If the old OCPP Charge Proxy integration (1.x) is still installed, the
  add-on leaves the sensors alone until you remove it (Settings > Devices &
  services). `sensor.ocpp_charge_proxy_energy` keeps its entity ID, so its
  Energy dashboard history carries on.
- Your power, SoC and car plugged in sensors are set up on the web page's
  **Settings** tab, and auto plug-in on the **Schedule** tab; the add-on
  reads them through Home Assistant's API.

## Web GUI

Open the add-on from the sidebar (or **Open Web UI**). It updates live and
follows your Home Assistant theme.

- **Overview:** state, power, current, SoC and energy; the current session;
  **smart charging** (the charge slots your supplier plans, found
  automatically from the Octopus Energy, EDF Energy or E.ON Next integration, also
  shown along the top of the chart);
  and a chart of power, current (with your max and the provider limit) or
  SoC over the last 30 minutes to 24 hours, or 14 days. Drag across the
  chart or scroll over it to zoom (double-click or **Reset zoom** to go
  back). The charts and the
  energy per day are read from Home Assistant's history of the add-on's
  sensors (keep them recorded): 10-second detail for 24 hours, then
  5-minute points while HA keeps them (10 days by default, `purge_keep_days`)
  and hourly beyond that.
- **Charge now** (**Settings** tab, Controls): click how long to plug in
  for (1 to 8 hours). It plugs in straight away and adjusts the schedule
  the same way auto plug-in does (see [Auto plug-in](#auto-plug-in)): a
  one-off slot you can change on the Schedule tab, the ready time set to
  its end, and it unplugs then.
- **Header:** a health dot left of the title (green / amber / red) that
  opens Diagnostics › Health.
- **Sessions:** energy and time spent charging per day for the last 14
  days (click a day to show only its sessions), and the last 20 charging
  sessions (energy, duration, peak power, what ended them; transaction ID
  and ID tag in the details), kept across restarts,
  and the last 20 plug-ins that never got a session: when, for how long, who
  plugged in, and whether auto re-plug gave up on it or it was unplugged
  first.
- **Schedule:** the plug-in schedule (see below), with a week view of when
  it has the car plugged in; Force schedule on supplier; auto plug-in and
  auto re-plug.
- **Settings:** controls for Plugged In, max current, a power override and a
  test SoC; the simulated car's start delay and ramp-up; and your power, SoC
  and car plugged in sensors, with their live values.
- **Diagnostics**, in three parts:
  - **Health:** version, uptime, reconnects and the last drop's reason,
    heartbeat and clock offset, the Home Assistant link and the add-on's
    Home Assistant entities, and any held messages.
  - **Messages:** the last 300 OCPP messages both ways, kept across
    restarts (with a marker where the add-on restarted), with a filter,
    full JSON on click and a Copy button for sharing.
  - **Provider:** what your provider has set: charging limits, charging
    profiles drawn as a timeline, the local authorisation list and every
    configuration key.

Times on the page are 24-hour. Longer explanations are behind **More**
links.

## Getting your OCPP credentials

Your provider will supply three values needed to connect:

- **Server hostname** — the OCPP WebSocket endpoint
- **Chargepoint ID** — your unique chargepoint identifier
- **Password** — authentication password

You may also need to set `charger_model` and `charger_vendor` to match a
charger model your provider supports. The defaults work for providers that
accept Wallbox chargepoints.

Check your provider's app or documentation for how to obtain these credentials.
