# Changelog

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
