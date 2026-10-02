# Changelog

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
