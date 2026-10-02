# Changelog

## 2.1.0

- **Status in the header:** "All good" or the number of issues (not
  connected to your provider, held messages, Home Assistant link down, old
  integration still installed, auto re-plug gave up). Click it to open the
  Health tab, which lists them under "Needs attention".
- **Phone-friendly tabs:** on narrow screens the tabs show icons with short
  labels and all fit on screen.
- **Chart:** shaded by state (charging, paused, waiting for a session), with
  session start and end marked. The chart's last 6 hours are kept across
  restarts (`/data/history.json`).
- **Sessions tab:** an "Energy per day" bar chart for the last 14 days (from
  the energy meter, kept in `/data/daily_energy.json`), and click any row for
  its details: start/end, meter readings, average power and its power curve
  (while within the chart's 6 hours).
- **Automation tab:** "Your week" shows when the schedule has the car plugged
  in each day, updating as you edit.
- **Settings tab:** one "Unsaved changes" bar with Save / Discard for the
  start-up, re-plug and sensor settings, instead of a Save button on each
  card. Plugged In, max current and the overrides still apply at once.

## 2.0.4

- The Home Assistant link and entities status moved from the Settings tab
  to the Health tab.

## 2.0.3

- **Start delay and ramp-up are now set on the web page** (Settings tab, new
  Simulated car card) instead of the add-on configuration. If you'd changed
  them from the defaults (3s and 5s), set them again there.
- **Auto re-plug is no longer in the add-on configuration**: turn it on/off
  and set the minutes and tries on the Settings tab. Changes you made there
  are kept; if you'd only changed them in the add-on configuration, set them
  again on the Settings tab (defaults: on, 10 minutes, 3 tries).
- **Plug-ins that never got a session are on the Sessions tab:** when
  Plugged In turns on but is turned off again before your provider starts a
  session, a "no session" row shows when, for how long, who plugged in
  (web page, Home Assistant, schedule, car plugged in sensor, auto plug-in,
  auto re-plug) and why it ended: re-plugged by auto re-plug because no
  session came, or unplugged before a session started (and by whom). A
  plug-in still waiting for a session shows at the top. The last 20 of these
  are kept, separately from the last 20 sessions.
- **The Messages tab is kept across restarts** (saved in
  `/data/messages.json` every minute and when the add-on stops), with an
  "Add-on restarted" line where each restart happened. Messages from an
  earlier day show their date.

## 2.0.2

- The Sessions tab shows each session's transaction ID and ID tag.

## 2.0.1

- **New Settings tab** on the web page: the controls (Plugged In, max
  current, power override, test SoC) moved there from the Overview tab, and
  the auto re-plug settings from the Automation tab. Overview now shows the
  charger's status, the current session and the chart; Automation is the
  plug-in schedule.
- **The Simulation tab is now part of Settings:** your power, SoC and car
  plugged in sensors, auto plug-in and the Home Assistant entities status are
  in the lower half of the Settings tab.

## 2.0.0

> **Upgrading from 1.x? After updating, do these steps:**
>
> 1. **Remove the integration.** Settings > Devices & services > OCPP Charge
>    Proxy > Delete, then remove OCPP Charge Proxy from HACS and restart Home
>    Assistant. Until it's removed, the add-on leaves the Power, Energy and
>    Current sensors alone.
> 2. **Restart the add-on.** It creates its own entities:
>    `input_boolean.ocpp_charge_proxy_plugged_in` and
>    `sensor.ocpp_charge_proxy_power` / `_energy` / `_current`. Energy keeps
>    its entity ID, so your Energy dashboard history carries on.
> 3. **Pick your sensors again.** Open the add-on's web page, **Simulation**
>    tab, and choose your power, SoC and car plugged in sensors and auto
>    plug-in settings. They aren't copied from the integration.
> 4. **Update your automations, scripts and dashboards:**
>    - `switch.ocpp_charge_proxy_plugged_in` is now
>      `input_boolean.ocpp_charge_proxy_plugged_in` (use
>      `input_boolean.turn_on` / `turn_off`).
>    - The State, Connected to Server, Last Heartbeat, Last Command, Power
>      Source, Reporting SoC, Monitored SoC sensors and the Current Amps
>      Setting select are gone; they're on the add-on's web page. For "is it
>      charging?" use `sensor.ocpp_charge_proxy_power` above 0 (with simulated
>      power).
> 5. **Check your max current** on the web page's Overview tab (it's kept, but
>    is now only set there).

**The companion integration is gone: the add-on does everything itself.**

- **Home Assistant entities from the add-on.** It creates a **Plugged In**
  helper, `input_boolean.ocpp_charge_proxy_plugged_in` (turn it on/off to plug
  in or unplug; it follows the add-on's own Plugged In), and keeps
  `sensor.ocpp_charge_proxy_power`, `_energy` and `_current` up to date. Energy
  keeps its entity ID, so the Energy dashboard history carries on. The sensors
  are unavailable while the add-on is stopped. While the old integration is
  still installed, the add-on leaves the sensors alone.
- **Automations need updating:** `switch.ocpp_charge_proxy_plugged_in` is now
  `input_boolean.ocpp_charge_proxy_plugged_in`, and the State, Connected to
  Server, Last Heartbeat, Last Command and SoC/power-source sensors are gone
  (they're on the add-on's web page). For "is it charging?", use the Power
  sensor: it's above 0 while charging (with the simulated power).
- **New Simulation tab: the add-on reads your sensors itself.** Pick your
  power (W or kW), SoC and car plugged in sensors and set up auto plug-in from
  lists of your HA sensors. The add-on follows them live through Home
  Assistant's API. Pick them again after updating: the integration's settings
  aren't copied across.
- **Plug-in schedule.** Switch Plugged In on or off at set times, on chosen
  days, as many times a day as you like (Automation tab). Times are in your
  Home Assistant time zone.
- **Auto re-plug.** If your provider hasn't started a session 10 minutes
  after Plugged In turns on, the add-on unplugs for 30 seconds and plugs back
  in, up to 3 times, then gives up until the car is next unplugged or a
  session starts. Re-plug After / Re-plug Tries are add-on options, and can be
  changed on the Automation tab too. The Overview tab shows when the next
  re-plug is due.
- **Max current is set on the add-on's web page** (Overview tab). The Current
  Amps option is still the starting value, and your current setting is kept.
- Settings are saved in `/data/automation.json` and `/data/sensors.json`.

## 1.1.0

- **New web GUI** (the add-on's page in the sidebar), with five tabs:
  - **Overview:** live state, power, current, SoC and energy; controls
    (Plugged In, max current, power override, test SoC); the current session;
    and a power / current / SoC chart for the last 30 min to 6 hours.
  - **Sessions:** the last 20 sessions with energy, duration, peak power and
    how they ended, saved in `/data/sessions.json`.
  - **Messages:** a live log of the last 300 OCPP messages, filterable, with
    the full JSON and a Copy button.
  - **Provider:** charging limits, charging profiles as a timeline, the local
    authorisation list and all configuration keys (what your provider set is
    marked).
  - **Health:** version, uptime, reconnects and the last disconnect reason,
    heartbeat and clock offset, HA integration push status, held messages.
- The page uses push updates instead of refreshing every 5 seconds, falling
  back to polling if the stream drops, and follows your HA theme.
- New read-only API endpoints for the page: `/api/messages`, `/api/sessions`,
  `/api/history`, `/api/provider` and `/api/health`.

## 1.0.5

- **Plugged In is remembered across an add-on restart**, like a cable left in
  a real charger. A restart mid-session still ends the session (StopTransaction,
  reason `Reboot`), but the charger now comes back as `Preparing` instead of
  `Available`, so your provider can start a new session. Before, Plugged In
  came back off and the car plugged in sensor didn't switch it back on, as it
  only reacts to off to on.
- The charger itself (connector 0) now always reports `Available` (or
  `Unavailable`) as OCPP 1.6 requires, never `Preparing` or `Charging`.

## 1.0.4

- Quieter logs during charging: periodic meter readings in a session (every
  60s with Octopus) and the replies to them are now logged at DEBUG too, like
  idle ones. Clock-aligned readings (every 15 min) stay at INFO, in a session
  or not.

## 1.0.3

- **SoC Source** is renamed **Reporting SoC** (matching "SoC sensor for
  reporting"). Existing installs keep the entity ID
  `sensor.ocpp_charge_proxy_soc_source`; new installs get
  `sensor.ocpp_charge_proxy_reporting_soc`.
- **Reporting SoC** and **Monitored SoC** now show the SoC itself when a
  sensor is set (e.g. `64%`), or `no reading` / `not set`, instead of
  `entity`. The number is also the `soc_percent` attribute, for automations.
  Monitored SoC's `source` attribute now says `reporting SoC sensor` when it
  watches the reporting sensor.

## 1.0.2

- **Monitored SoC** now shows where auto plug-in's SoC comes from, with the
  same states as SoC Source: `entity` (a sensor is being watched and has a
  value), `no reading` (a sensor is set but has no usable value) or `not set`
  (no sensor to watch). It previously showed the SoC itself, so it read
  "unknown" whenever there was nothing to watch. The SoC is now the
  `soc_percent` attribute, alongside `entity_id`, `source`, `auto_plug`,
  `threshold` and `armed`.
- Clearer option names in the integration's settings: "Car battery (SoC)
  sensor" is now **SoC sensor for reporting to your OCPP provider**, "Car
  connected sensor" is now **Car plugged in sensor**, and "Plug in
  automatically when the car's SoC drops low" is now **Plug in automatically
  when the SoC drops low**. Only the labels changed: saved settings are kept.

## 1.0.1

- Quieter logs: idle meter readings (the periodic one every 60s with Octopus
  while no session is running) and the server's replies to them are now
  logged at DEBUG instead of INFO, like Heartbeats. They show with
  `log_level: debug`. Clock-aligned readings (every 15 min with Octopus),
  readings during a charging session, and all other OCPP messages
  (Start/StopTransaction, StatusNotification, the provider's commands...)
  are still logged at INFO.

## 1.0.0

First stable release. Also includes the changes planned as 0.9.9, which
wasn't released on its own.

- New integration option: **car connected sensor**. Pick a binary sensor
  (e.g. your car's "charging cable connected") and Plugged In is switched on
  when it changes from off to on. It never switches Plugged In off. Readings
  of unavailable/unknown in between are ignored (on -> unavailable -> on isn't
  a new connection), and the first reading after a restart doesn't plug in.
  The Plugged In switch stays usable by hand, and it works alongside auto
  plug-in.
- New: **charging taper near full**. With a car battery (SoC) sensor set,
  simulated power stays at full up to 90% SoC, then tapers linearly to 30%
  of full power at 100%, like a real car's charge curve. The energy register
  follows the tapered power. Not applied when power comes from a power
  sensor (that already shows the car's real taper), or without a SoC sensor.
- New: **integration tests** in CI, using pytest-homeassistant-custom-component
  (a real Home Assistant core): config and options flows, entity setup,
  the car connected sensor, the manual switch, auto plug-in and SoC
  reporting. Run with `python -m pytest tests/ -o asyncio_mode=auto` from the
  repository root.
- The integration's IoT class is now `local_push` (it receives push updates
  from the add-on since 0.9.4).

- Faster recovery after an add-on restart. The integration took around 40s
  to come back (entities unavailable meanwhile): its reconnect delay doubled
  from 5s (5, 10, 20s...), and the fallback poll stayed on the 5-minute
  schedule used while push updates work. It now retries the event stream
  after 1, 2, 2, 3, 3, then 5s (backing off to at most 60s if the add-on stays
  down) and polls every 10s straight away when push updates drop, so
  entities are back within a few seconds of the add-on starting.
- New diagnostic sensor **Last Heartbeat**: when the provider last answered
  a Heartbeat (a timestamp, so it reads "10 seconds ago"; if it stops moving,
  the link is down). Attributes: `round_trip_ms`, `interval_s`, `server_time`
  and `clock_offset_s` (how far the provider's clock is from yours).
- **Last Command Received / Sent** have more attributes (the state is still
  the action): `summary` (one readable line, e.g. `chargingALimitConn1 = 32`
  or `transaction 1, meterStop 6612523 Wh, EVDisconnected`), `round_trip_ms`
  (the provider's response time for sent commands, ours for received ones),
  `message_id` (to match the add-on log) and `recent` (the last 10 commands
  that way, newest first, with time, summary and status).
- The add-on status page shows the last heartbeat (with a warning if it's
  overdue) and each command's summary and response time.
- The **State** sensor is renamed **OCPP Charge Proxy State** (also on the
  device page, where it showed just "State"). Its values and entity ID
  (`sensor.ocpp_charge_proxy_state`) are unchanged, so automations keep
  working.
- **Power Source** and **SoC Source** are now diagnostic sensors, listed with
  the other diagnostics on the device page. Their values and entity IDs are
  unchanged.
- New diagnostic sensor **Monitored SoC**: the SoC (%) that auto plug-in
  watches (the separate monitor sensor if set, otherwise the reported SoC
  sensor), updating as soon as that sensor changes. Attributes: `entity_id`,
  `source` (`monitor sensor` / `reported SoC sensor`), `auto_plug` (on/off),
  `threshold` and `armed` (whether the next drop below the threshold will
  plug in). Unknown when there's no sensor to watch.

## 0.9.8

- Quieter logs: Heartbeat messages (every 10s with Octopus) and the server's
  replies to them are now logged at DEBUG instead of INFO, so they only show
  with `log_level: debug`. All other OCPP messages are still logged at INFO.
- Tests: fixed `test_power_source_shows_entity_while_idle` (0.9.7), which
  sent a real message with no server to answer and timed out after 30s on CI.

## 0.9.7

- Fix: after an add-on restart, the power and SoC sensor values weren't sent
  to the add-on until the sensor changed or the integration next polled (every
  5 minutes while push updates are working), so the add-on ran on the
  simulation in the meantime. Toggling a switch forced a refresh, which is
  why it came right then. The integration now re-sends both as soon as it
  reconnects to the add-on.
- Fix: **Power Source** only showed `entity` while charging and reset to
  `simulated` whenever the charger was idle, even with a power sensor set.
  It now shows whether a power sensor value is in use (`entity`) or not
  (`simulated`), charging or not.

## 0.9.6

- New integration option: **plug in automatically when the car's SoC drops
  low**, with an adjustable threshold (1-99%, default 30%). Off by default.
  When the watched SoC drops below the threshold, Plugged In is switched on,
  so the provider can schedule a charge.
- It can watch its own SoC sensor, separate from the one reported to the
  provider: useful when the car may be away from home, where its SoC
  shouldn't be reported as the charging car's. The watched sensor is never
  sent to the provider. Left empty, it watches the reported SoC sensor.
- It triggers on the drop, not while the SoC is low: if you unplug by hand at
  a low SoC it won't plug straight back in, and restarting Home Assistant with
  a low SoC doesn't plug in either. It re-arms once the SoC is back at or
  above the threshold. Nothing happens if already plugged in.

## 0.9.5

- New integration sensor **SoC Source**, alongside Power Source. Shows where
  the SoC sent to the provider comes from: `entity` (your car battery sensor
  has a value and it's being reported), `no reading` (a sensor is set but has
  no usable value right now, so no SoC is sent) or `not set` (no sensor: SoC
  is never reported and car full is off). There is no simulated SoC, so the
  proxy never makes one up. Attributes: `entity_id` and `soc_percent`.
- Fix: the **Current Amps Setting** in Home Assistant was overwritten by the
  provider. Octopus sends `chargingALimitConn1 = 32` at every boot, start and
  stop, which reset the charger to 32 A. The HA setting is now the charger's
  maximum, like a real Wallbox's max-current setting: the provider's limit can
  lower the current below it but never raise it, and the charger uses the
  lower of the two (snapped down to a supported setting, 6 A minimum). The
  provider's value is still accepted and reported back to it. The select's
  attributes show `effective_amps` and `provider_limit_amps`; the status page
  shows the current in use.
- The HA current setting is now remembered across add-on restarts
  (`/data/current_setting.json`). The add-on's `current_amps` option is the
  starting value; changing that option later takes over again.

## 0.9.4

- Fix: crash-safe storage. The energy register (and the offline queue,
  open transaction and serial) is now written to a temp file, flushed to disk
  and swapped in atomically, with a `.bak` copy of the previous version. A
  power cut mid-write could previously leave a half-written file, which was
  read back as 0, resetting the meter for both the provider and the Energy
  dashboard. If the main file is ever unreadable, the backup is used.
- New: optional **car battery (SoC) sensor** in the integration's settings,
  alongside the power sensor. When set, the car's SoC is sent to the provider
  in meter values (when requested, while a car is plugged in, location `EV`,
  unit `Percent`). When unset, nothing is reported. Fields can now be cleared
  to unset a sensor (previously a set power sensor couldn't be removed).
- New: **car full**. With a SoC sensor set and reading 100% mid-session, the
  charger reports `SuspendedEV` and stops drawing power, with the session
  kept open; it resumes charging if the SoC drops below 100%. A
  charging-profile pause (`SuspendedEVSE`) takes priority. Plugging in an
  already-full car goes Charging -> SuspendedEV. No SoC sensor = never full.
- New: **push updates**. The add-on streams its state to the integration
  (`/api/events`, Server-Sent Events): state, plug, connection and command
  changes arrive within about a second, and live power every 10s. Power and
  SoC sensor changes are pushed to the add-on straight away. Polling every
  10s remains as the fallback (and with older add-ons).
- Add-on status page now also shows power, energy, car SoC, the transaction,
  held messages, and the last command received/sent, refreshing every 5s.
- Tests: two RemoteStart/RemoteStop tests no longer leave a call running
  after they finish (the "coroutine 'ChargePoint.call' was never awaited"
  warning), and now also check the start/stop actually happened.

## 0.9.3

- Live power in Home Assistant. Power, Current and the other live figures were
  only refreshed at each meter reading (every 60s with Octopus), so HA showed
  0 W for the first minute of a charge and never showed the start delay or
  ramp-up. `/api/state` now works out the current power on every poll, so the
  sensors follow the delay, the ramp, charging-profile pauses and current
  changes within one integration update (10s).
- Display only: the energy register and the MeterValues sent to the server
  are unchanged and still integrate exactly between readings.

## 0.9.2

- New integration sensors **Last Command Received** and **Last Command Sent**
  (diagnostic). The state is the OCPP action (e.g. `RemoteStartTransaction`,
  `StatusNotification`). Attributes hold the `timestamp`, the `payload`, the
  `response`, and its `status` (e.g. `Accepted`, `Rejected`, or
  `Error: <code>`; `OK` for replies without a status). Bulky lists such as
  transactionData are shown as a count.
- Received covers every command from the server. Sent leaves out the routine
  Heartbeat and MeterValues. Held messages appear once they're actually sent
  after reconnecting.
- The add-on API `/api/state` now includes `last_command_received` and
  `last_command_sent`.

## 0.9.1

- New: transactions interrupted by a power cut or crash are now closed. While
  a transaction is open it is saved to `/data/active_transaction.json` (id,
  idTag, last meter reading and its time), updated on every reading. If the
  add-on starts and finds one still open, it holds a StopTransaction with
  reason `PowerLoss`, using the last saved reading as `meterStop` and its time
  as the timestamp, and sends it after the next BootNotification, as a real
  charger does after losing power. `transactionData` is included when
  `StopTxnSampledData` was set.
- A StopTransaction cut off before it could be queued (for example a shutdown
  that timed out while sending the Finishing status) is now recovered the same
  way, rather than lost.
- If the interrupted transaction's StartTransaction was itself still held, the
  PowerLoss stop is renumbered with the server's id once StartTransaction is
  accepted. A transaction that already has a held StopTransaction isn't
  stopped twice.
- Changed: `StopTxnSampledData` now defaults to empty (was
  `Energy.Active.Import.Register`), matching Wallbox Pulsar Plus firmware, so
  StopTransaction only includes `transactionData` once the server sets
  `StopTxnSampledData` or `StopTxnAlignedData` with ChangeConfiguration.

## 0.9.0

- New: messages are held while offline. If the connection to the OCPP server
  drops mid-charge, charging carries on (energy register, meter readings,
  charging profile) and the transaction stays open. StartTransaction,
  StopTransaction and MeterValues for the transaction are held in order and
  sent as soon as BootNotification is accepted on reconnect, before the status
  updates. Like a real charger, StatusNotifications, Heartbeats and idle meter
  readings are not held; the current status is sent on reconnect instead.
- Held messages are saved to `/data/offline_queue.json`, so they survive an
  add-on restart. Stopping the add-on while offline holds the StopTransaction
  (reason `Reboot`) for the next connection.
- If a transaction starts while the server is unreachable, it uses a
  provisional id until StartTransaction is accepted. Held messages for that
  transaction are then renumbered with the id the server assigns.
- A call in flight when the connection drops now fails at once and is held,
  instead of waiting 30s and blocking the next connection's BootNotification.
- Up to 1,000 messages are held. Beyond that the oldest MeterValues are
  dropped; StartTransaction and StopTransaction are never dropped.
- New: StopTransaction `transactionData`. Readings selected by the new
  `StopTxnSampledData` key (default `Energy.Active.Import.Register`) are taken
  at the start (`Transaction.Begin`), every `MeterValueSampleInterval`
  (`Sample.Periodic`) and at the stop (`Transaction.End`), plus
  `StopTxnAlignedData` (default empty) on clock-aligned boundaries
  (`Sample.Clock`). The server can change both keys with ChangeConfiguration.
  The list is capped at 100 readings; beyond that the resolution is halved,
  and the Begin and End readings are always kept. Set both keys empty to send
  no transactionData.

## 0.8.0

- New: realistic charging start. After StartTransaction (or resuming from a
  charging-profile pause) the simulated car now waits `start_delay_s`
  (default 3s) before drawing current, then ramps linearly to full power over
  `ramp_up_s` (default 5s), instead of jumping straight to full power. Set
  both to 0 for the old behaviour.
- The energy register integrates over the delay and ramp exactly, so a 60s
  meter interval spanning the start no longer bills the first few seconds at
  full power.
- Power from a real power entity (integration override) is unaffected, as it
  already reflects the car's real ramp-up.

## 0.7.1

- Fix: Home Assistant Energy dashboard spike after every add-on restart. The API
  reported `energy_kwh = 0` until the first meter reading (~60s after boot), so
  HA's total-increasing Energy sensor saw the register drop to 0 and recorded the
  climb back (the entire lifetime register, ~6,500 kWh) as new consumption. The
  stored register is now reported from startup.

## 0.7.0

OCPP 1.6 conformance fixes:

- StartTransaction now uses the idTag from RemoteStartTransaction (was a fixed
  `NoAuthorization`), and StopTransaction uses the session's own idTag (was
  hard-coded).
- Start sequence is now Preparing -> StartTransaction -> Charging. Removed the
  spurious Available / SuspendedEV statuses and the mid-start connector 0 status.
- A BootNotification requested via TriggerMessage now re-sends the real charger
  identity (was an empty model and vendor), adopts the heartbeat interval from
  the reply, and doesn't repeat the boot status sequence.
- Empty optional fields are no longer sent: BootNotification `iccid`, `imsi`,
  `meterSerialNumber` (and serial/firmware when blank), StatusNotification
  `info`, `vendorId`, `vendorErrorCode`, and StopTransaction `transactionData`.
- Periodic MeterValues now follow `MeterValuesSampledData` (requested measurands,
  in order; unavailable ones such as SoC skipped) and carry the transactionId
  whenever a transaction is open, including while paused by a charging profile.
- Configuration keys the proxy doesn't model (e.g. vendor keys `minSoC`, `maxSoC`,
  `AuthEnabledOffline`) are still accepted, and are now stored and reported by
  GetConfiguration.

## 0.6.1

- StopTransaction reason now reflects how the charge ended: `EVDisconnected`
  when unplugged from Home Assistant, `UnlockCommand` for UnlockConnector,
  `SoftReset` / `HardReset` for Reset (previously all `Remote`).

## 0.6.0

- Fix: phantom energy at the start of every charge. The first reading after a
  start multiplied the idle time since the previous reading (up to 60s) by the
  new charging power, adding ~120 Wh before any charging happened. Energy is now
  checkpointed at every charging state change (start, stop, profile pause/resume,
  UnlockConnector).
- Fix: `meterStop` now includes the energy delivered since the last periodic
  reading (previously up to 60s of charging was dropped).
- Safeguard: `initial_energy_wh` is only applied if it's higher than the stored
  energy register, so a value left in the options can never move the meter
  backwards. A warning is logged when it's ignored.

## 0.5.4

- Fix: integration setup now finds the add-on automatically. Add-ons installed from
  a repository get a hostname with a repository prefix (e.g.
  `e504bcf9-ocpp-charge-proxy`), so the previous guesses (`ocpp-charge-proxy`,
  `localhost`) failed with "Cannot connect". The installed add-on's slug is now
  looked up from the Supervisor and the URL pre-filled.
- Clearer setup text and error message pointing at the Hostname on the add-on's
  Info page.

## 0.5.3

- Release to trigger the first add-on image build on this repository
  (GitHub Actions were disabled on the fork). No code changes.

## 0.5.2

- Fix: repository owner typo (`thewhalw21` -> `thewhale21`) in the add-on image name,
  repository URLs, integration manifest and README links. With the wrong owner the
  add-on image could not be pulled, so the add-on could not update.

## 0.5.0

- New: clock-aligned meter values. When the server sets `ClockAlignedDataInterval`
  (Octopus uses 900s), a `MeterValues` with context `Sample.Clock` is sent on each
  boundary from UTC midnight (:00, :15, :30, :45), containing the measurands listed
  in `MeterValuesAlignedData`. Includes the transactionId during a transaction.
- `ClockAlignedDataInterval` is now reported by GetConfiguration; `0` disables.
  Invalid values are rejected.
- Refactor: energy accumulation is shared between periodic and clock-aligned
  readings so energy is never double-counted. Periodic meter values are unchanged.

## 0.4.0

- Fix: `HeartbeatInterval` now reflects the interval actually in use. The value from
  an accepted BootNotification is applied and reported by GetConfiguration
  (previously it always reported the hard-coded `30`).
- `ChangeConfiguration HeartbeatInterval` now takes effect immediately, interrupting
  the current wait. Invalid values (non-numeric or < 1) are rejected.

## 0.3.0

- Fix: graceful shutdown on add-on stop/restart. SIGTERM is now handled inside the
  event loop, so the proxy stops any active transaction (reason `Reboot`) and sends
  a `StatusNotification: Unavailable` to the server before the socket closes.
  Previously the process was killed before either message was sent.
- Shutdown also interrupts the reconnect backoff and an in-progress BootNotification
  instead of waiting them out.

## 0.2.0

- Fix: stale heartbeat/meter-value loops kept running after a reconnect, spamming
  `ConnectionClosedOK` warnings. All per-connection tasks are now cancelled when the
  connection drops, and a clean server close (1000) triggers a reconnect.
- Workaround: accept RemoteStopTransaction when the server's transactionId doesn't
  match the active transaction (seen with Octopus sending `1` instead of the issued id).

## 0.1.0

- Initial release
- OCPP 1.6 chargepoint proxy for smart tariff providers
- Full OCPP message handler coverage: BootNotification, Heartbeat, MeterValues,
  StatusNotification, RemoteStart/StopTransaction, SetChargingProfile,
  ClearChargingProfile, GetConfiguration, ChangeConfiguration, TriggerMessage,
  ChangeAvailability, UnlockConnector, Reset, ClearCache, SendLocalList,
  GetLocalListVersion, DataTransfer
- Configurable charger identity (vendor, model, serial, firmware)
- Realistic power delivery simulation
- Power entity support: report real power from any HA sensor
- Companion HA integration with entities for automations and energy dashboard
- Ingress web UI for status monitoring
- Security score 8/8
