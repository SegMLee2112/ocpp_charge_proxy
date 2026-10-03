# Changelog

## 2.12.2

- Auto plug-in: Octopus's 6-hour limit (moving the next scheduled slot) now
  only applies while Force schedule on supplier is on, as for the schedule.
  With it off, the schedule and auto plug-in can plug in for longer

## 2.12.1

- One-off schedule times (and skips) are kept for 14 days after they run
  (was a day). They're hidden from the Schedule tab's list once run, and
  sessions on the Sessions tab that ran in a one-off slot are tagged
  **One-off** or **Auto plug-in**

## 2.12.0

- Auto plug-in: new switch **Automatically adjust schedule to fit auto
  plug-in** with **Charge for** (hours). When auto plug-in plugs in, the
  charge is added to the schedule as a one-off, unplugging at the first
  ready time the supplier accepts after those hours, and the supplier's
  ready time is set. With Octopus, if that takes the day over 6 hours, the
  next scheduled slot's first hours move to it; if it meets the next slot,
  they become one. Its one-offs run even with the schedule off
- One-off schedule times are now kept for a day after they run (was 5
  minutes), so the slot they belong to stays known

## 2.11.0

- An add-on restart (e.g. an update) no longer ends the charging session:
  it's left open and carried on when the add-on is back within 10 minutes,
  like a charger that briefly lost its connection. Octopus only starts a
  new session at the next hour or half hour, so ending it lost up to 30
  minutes of charging. If the supplier starts a new session instead, the
  old one is closed first. New option `continue_session_on_restart` (on by
  default) to go back to ending it (`Reboot`)

## 2.10.3

- Smart charging card: the slot running now shows its start and end, the
  energy planned for it and when it ends. Below it, "After this slot" (was
  "Planned", which read "None planned yet" while a slot was running)
- Smart charging card: the schedule check (Force schedule on supplier):
  matches / doesn't match / checking, with what's wrong, and a link to the
  Schedule tab

## 2.10.2

- Octopus / EDF: the slot running now and the next slots come from the
  current plan only. A started dispatch keeps its original times after the
  supplier re-plans (e.g. after a restart mid-slot), so it showed a slot
  "now, until 10:00 PM" when the next one started at 17:00. Started
  dispatches are no longer used (also not on the chart)

## 2.10.1

- New status **Waiting for supplier** (amber): plugged in, your supplier's
  slot is running now, but no session has started. **Scheduled** now only
  means a slot is planned for later
- Auto re-plug no longer treats a running slot as an answer: with no
  session the set minutes after the next half hour (Octopus may only start
  on the hour or half hour), it re-plugs. Covers the add-on restarting
  mid-slot, which ends the session (as a charger reboot does)

## 2.10.0

- Force schedule on supplier: the supplier's plan is checked against the
  schedule while plugged in, up to the ready time set for that stretch
  (each stretch is checked on its own, from its plug-in). A slot running
  past the unplug, or a ready time changed on the supplier's side, is
  flagged on the Schedule tab, the Overview and in the log
- The wait for the supplier to stop a session at a scheduled unplug can be
  set (0 to 600 s, default 60) under the Force schedule on supplier switch
- The add-on now follows the supplier's ready time entity live
- Tests on GitHub also run for tags and on demand, install from
  requirements-dev.txt (now including pytest-aiohttp), and cache pip

## 2.9.4

- Force schedule on supplier: at a scheduled unplug during a session, the
  add-on now gives your supplier up to 1 minute to stop the session itself
  before unplugging (it unplugs as soon as the session ends, or after the
  minute). The Overview shows an "Unplugging by …" chip while it waits

## 2.9.3

- The skip panel's line is shorter: "Slot: 03/10 16:00 → 03/10 22:00"
  ("Skipped slot: …" when skipped).

## 2.9.2

- The skip panel in **Next 7 days** opens right under the row of the slot
  you clicked, instead of at the bottom of the card.
- It stays open and updates straight away after **Skip this slot** or
  **Undo skip** (it used to close, and only showed the change when the
  slot was clicked again).

## 2.9.1

- **Skip a slot from the week view:** click a slot in **Next 7 days** and
  choose **Skip this slot** to skip it once, both its plug-in and its
  unplug. Skipped slots show hatched; click one and **Undo skip** to put it
  back. This replaces the Coming up list, which is gone.

## 2.9.0

- **One-off times:** **+ Add a one-off** on the Schedule tab adds a plug-in
  or unplug for a single date (e.g. unplug at 06:00 next Thursday for an
  early start). It runs once, alongside the weekly times, and is removed
  after it has run.
- **Skip once:** a new **Coming up** card lists the next 7 days of
  schedule times (weekly and one-off). **Skip** stops one of them running
  that once, **Undo** puts it back. A skipped unplug isn't used for the
  supplier ready time (the next one is), and a skipped plug-in doesn't
  count at start-up. Skips are forgotten a day after.
- **Next 7 days:** the week view now shows the actual coming week, from
  today, with one-off times and skips included (it was a Monday-to-Sunday
  pattern). Octopus's 6-hour check uses the same coming week.

## 2.8.0

- **Start-up check for the schedule.** If the add-on starts (or restarts,
  e.g. after an update) inside a stretch the schedule has the car plugged
  in, say at 02:00 with plug in 23:30 and unplug 07:00, and Plugged In is
  off, it plugs in straight away instead of waiting for the next plug-in
  time. With Force schedule on supplier on, it also sets your supplier's
  ready time, trying for up to 3 minutes while Home Assistant connects.
  The Schedule tab shows it as the last run "(when the add-on started)".
  It only plugs in, never unplugs, and only while the schedule is on. If
  you'd unplugged by hand inside the stretch before the restart, it plugs
  back in.

## 2.7.6

- The **Automation** tab is now called **Schedule**. Links to `#automation`
  still work, and `#schedule` opens it too.

## 2.7.5

- The Automation tab's "Set my supplier's ready time" switch is now called
  **Force schedule on supplier**. It works the same.

## 2.7.4

- Octopus's 6-hours-a-day limit only applies while **Set my supplier's
  ready time** is on. With it off, the schedule can plug in for as long
  as you like, with no red marks or warning.

## 2.7.3

- **Octopus's 6 hours a day is enforced.** With the Octopus Energy
  integration found, a schedule that has the car plugged in for more than
  6 hours in any 24 hours (across midnight too) can't be saved: the
  stretches that go over show in red in Your week, the plug-in and unplug
  times that make them are marked in red in the schedule, and Save says
  what to shorten. Turning the ready time on is refused while the saved
  schedule goes over. Switching the schedule on or off is always allowed.
  Other suppliers aren't limited.

## 2.7.2

- While the schedule sets your supplier's ready time, **unplug times are
  limited to the ready times your supplier accepts**: on the hour or half
  hour, and for EDF Energy from 04:00 to 11:00 (Octopus Energy: any time
  of day). The time picker steps in 30 minutes within that range, unplug
  times outside it are marked in red with a note, and the schedule won't
  save until they're changed. Turning the ready time on is refused while
  the saved schedule has unplug times outside it. Plug-in times aren't
  limited. If the integration has a select entity, its list of times is
  what's allowed.

## 2.7.1

- **Octopus ready times at any time of day:** Octopus now accepts ready
  times round the clock (in 30-minute steps), so the schedule's unplug time
  is used as it is: plugged in 4pm to 10pm sets 22:00, and 10:00 to 12:00
  sets 12:00. EDF Energy stays 04:00 to 11:00. If the integration offers a
  list of times (its select entity), that list still decides.
- **Your week** shows the schedule in your supplier's colour while the
  ready time is set from it: purple for Octopus Energy, yellow for EDF
  Energy, red for E.ON Next.
- The **6-hour warning** only shows with Octopus Energy (it's Octopus's
  daily smart charging cap).

## 2.7.0

- **Ready time from the schedule** (Automation tab, a switch, off by
  default). When the schedule plugs in, the add-on sets your supplier's
  smart charging ready-by time to the schedule's next unplug: with 02:00 to
  04:00, 06:00 to 08:00 and 10:00 to 12:00 it sets 04:00, then 08:00, then
  11:00. It's only set at scheduled plug-ins, never otherwise.
  - Octopus Energy and EDF Energy accept 04:00 to 11:00 in 30-minute
    steps: the latest of those at or before the unplug is used. If there's
    none (e.g. plugged in 4pm to 10pm) nothing is set and the page says why.
  - E.ON Next's integration has no ready time setting, so it can't be used
    there.
  - The last time it was set (or why not) is shown under the switch.
- **6-hour warning:** the Your week card warns when the schedule has the
  car plugged in for more than 6 hours in any 24 hours, as your supplier
  may not schedule more smart charging than that in a day.

## 2.6.2

- Supplier slots on the History chart are drawn in the supplier's colour:
  purple for Octopus Energy, yellow for EDF Energy, red for E.ON Next
  (other suppliers: blue).

## 2.6.1

- The **Health** tab shows whether your supplier's smart charging
  integration was found (Octopus Energy, EDF Energy or E.ON Next), which
  sensor the add-on follows, any others found, and when it last looked
  (it looks again every 10 minutes).

## 2.6.0

- **Scheduled status.** While the car is plugged in and your supplier has a
  charge slot planned, the add-on's status shows **Scheduled** (with the
  next slot under it) instead of Preparing, on the Overview tab, in the
  History chart's shading and in `sensor.ocpp_charge_proxy_status`. What
  the charger reports to the OCPP server doesn't change.
- **Auto re-plug understands schedules.** If your supplier's plan is found,
  a planned slot counts as an answer: no re-plug while one is planned (e.g.
  plugged in at 6pm for a slot at 11:30pm), and a re-plug only when nothing
  has been scheduled the set minutes after plugging in. Without a supplier
  integration it works as before (waits for a session).
- **E.ON Next** smart charging is found too (the eon_next integration's
  "Smart Charging Schedule" sensor), alongside Octopus Energy and EDF Energy.
- The supplier's sensor is followed live (found when the add-on connects to
  Home Assistant and looked for again every 10 minutes), rather than read
  from all of HA's states each time.

## 2.5.0

- **Smart charging card** on the Overview tab: the charge slots your
  supplier plans for the car, whether one is running now, and how much
  energy each should deliver. Found automatically: the add-on looks for the
  dispatching sensor of the Octopus Energy integration
  (`binary_sensor.octopus_energy_*_intelligent_dispatching`) or the EDF
  Energy one (`binary_sensor.edf_energy_*_intelligent_dispatching`), or any
  sensor with the same `planned_dispatches` attribute. Nothing to set up;
  if none is found the card says "Smart charging information not found".
- The History chart shows your supplier's slots (completed and planned) as
  a strip along the top, so you can compare what was planned with what
  charged.

## 2.4.1

Cleanup, no change to what the add-on does:

- Removed files no longer used: the old Home Assistant bridge, the
  interactive console and run_standalone.sh (the add-on only runs under
  Home Assistant).
- Removed what was left for the old companion integration: its event
  stream and its one-off settings migration. (The warning if the old
  integration is still installed stays.)
- The start delay / ramp-up and auto re-plug options from before 2.0.3 are
  no longer read. If you changed them then and never saved the Settings
  tab since, check them there.
- Tidied code comments.

## 2.4.0

- **Zoom on the History chart.** Drag across the chart to zoom into that
  stretch, or scroll over it to zoom in and out around the pointer (from 2
  minutes up to 14 days). Double-click or **Reset zoom** goes back to the
  selected range; picking a range does too. Zooming further back than the
  10-second readings switches to the 5-minute / hourly points by itself.
- **Time spent charging per day** on the Sessions tab: the per-day chart
  has an **Energy / Time charging** switch (remembered in your browser),
  and hovering over a bar shows both. Charging time comes from the Status
  sensor's history in Home Assistant; days before 2.3.0 are estimated from
  the sessions' lengths (shown faded), so they include any paused time.

## 2.3.0

- **Charts and daily energy now come from Home Assistant's history**
  instead of the add-on's own files. The add-on keeps only the last hour in
  memory; older chart data, the 14-day view, session power curves and the
  energy per day are read from what HA's recorder already keeps for the
  add-on's sensors. Energy per day now matches the Energy dashboard.
- Two new sensors, so HA records everything the charts show:
  `sensor.ocpp_charge_proxy_status` (the OCPP state: Charging, Preparing...)
  and `sensor.ocpp_charge_proxy_current_limit` (the current the charger
  uses, with your max and the provider's limit as attributes).
- The 14-day view and older session curves use HA's 5-minute statistics
  (was 2-minute averages), and hourly ones beyond HA's recorder retention
  (10 days unless you've changed `purge_keep_days`).
- history.json, history_long.json and daily_energy.json are deleted on the
  first start. Sessions, messages and settings stay in the add-on's files.
- The chart's state shading is drawn as one block per state, so long
  views are no longer darker than short ones.

> **After updating:** the state shading and limit lines only exist in HA
> from this version on, so older parts of the charts show power and current
> without them. If you exclude sensors from HA's recorder, keep the
> `sensor.ocpp_charge_proxy_*` ones recorded or the charts will be empty
> beyond the last hour.

## 2.2.1

- The History chart no longer writes "Session start" / "Session end" on
  the chart (they overlapped when sessions were close together). The
  dotted lines stay; hover near one to see which it is and when.

## 2.2.0

- **History chart: 12h, 24h and 14d views.** The 10-second readings are now
  kept for 24 hours (was 6), and 2-minute averages, with each one's peak,
  for 14 days. The 14d view uses the averages; hover over it for the peak.
  The time axis shows days on the longer views.
- **Power curves for older sessions.** Opening a session on the Sessions
  tab shows its power curve for any session in the last 14 days (was 6
  hours). Sessions from the last day use the 10-second readings; older ones
  the 2-minute averages.
- The **Hide Heartbeat** / **Hide MeterValues** (Messages) and **Set by
  provider only** (Provider) tick boxes are remembered in your browser, so
  they stay as you left them after a reload or restart. **Pause** is not
  remembered.
- The 14-day averages are saved in history_long.json in the add-on's data
  folder (about 1–2 MB when full). On the first start after updating it's
  filled in from the history already kept, so the 14d view starts with the
  last 6 hours and grows from there.

## 2.1.8

- The web page is no longer cached by the browser, so an update shows
  straight away. Before, the browser could keep showing the previous
  version's page (e.g. the "All good" badge instead of the 2.1.3 status dot)
  until a hard refresh (Ctrl+F5).

## 2.1.7

- The sensor lists on the Settings tab can be searched: click one and type
  part of a sensor's name, entity ID or reading to narrow the list. Use the
  arrow keys and Enter, or click, to choose. Esc leaves it unchanged.

## 2.1.6

- Quieter add-on log: the web page's routine requests (it refreshes every
  few seconds while open) are now logged at debug level only. Plug, unplug
  and settings changes, and any failed request, still show.
- If the web page's live connection drops and the browser gives up on it,
  the page now reopens it instead of polling every 5 seconds until reloaded.

## 2.1.5

- After the server stops a charge (RemoteStopTransaction), the charger now
  tells it the car is still plugged in (**Preparing**) once StopTransaction
  is done. Before, the last status the server saw was **Finishing**. After an
  UnlockConnector the charger likewise reports **Available**.
- Clearer log line when the server sets a current limit above your max:
  "Provider limit 32A is above your max 6A: next charge will run at 6A" when
  nothing is charging. It only sets the limit; it doesn't start a charge.

## 2.1.4

- On the Sessions tab the current session can be clicked for its details
  too: start time, meter reading now, energy so far, average and peak power,
  and its power curve so far.

## 2.1.3

- The health status is now a larger coloured dot to the left of the title
  (green: healthy, amber/red: unhealthy), without words. Hover over it to see
  any issues; click it to open the Health tab.

## 2.1.2

- The status button in the header says **Healthy** or **Unhealthy** (hover
  over it to see the issues). It still opens the Health tab.

## 2.1.1

- **Energy per day** fills in days from the kept sessions (each session's
  energy on the day it started) where the meter-based figure is missing or
  lower, so sessions from before 2.1.0, or before a restart earlier in the
  day, show in the bars.

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
