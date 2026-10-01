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

It consists of two components:

- **Add-on** — runs the OCPP client (Docker container managed by HA Supervisor)
- **Integration** (HACS) — exposes entities for automations, dashboards, and the energy dashboard

Both are installed from this repository.

## Step 1: Install the Add-on

1. Add this repository to your Home Assistant add-on store:

   [![Add repository][repository-badge]][repository-url]

   Or manually: **Settings > Add-ons > Add-on Store > ... > Repositories** and
   add this repository URL.

2. Install the **OCPP Charge Proxy** add-on
3. Configure your OCPP credentials (server hostname, chargepoint ID, password)
4. Start the add-on

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
5. Optionally select a **power sensor** entity (e.g. your battery charge power
   or grid demand sensor) — the proxy will report real power values to your
   provider instead of simulated ones

### Entities provided

| Entity | Type | Description |
|--------|------|-------------|
| Plugged In | Switch | Simulate car plugged in/unplugged |
| Current Amps Setting | Select | Set charger current (6-32A) |
| State | Sensor | OCPP state (Available/Preparing/Charging/etc.) |
| Power | Sensor | Current power draw (kW) |
| Energy | Sensor | Cumulative energy (kWh, energy dashboard compatible) |
| Current | Sensor | Current draw (A) |
| Power Source | Sensor | Whether using real entity or simulated values |
| Connected to Server | Binary Sensor | Connected to OCPP server |

## Usage

1. Start the add-on and verify it connects (check the add-on logs)
2. Toggle the **Plugged In** switch to simulate connecting a car
3. Set a departure time and charge amount in your provider's app
4. Your provider will schedule charging and send start/stop commands
5. Create automations based on the **State** sensor to control your actual
   charger (e.g. turn on a smart plug when State changes to `Charging`)

## Documentation

See the [add-on documentation][docs] for full configuration details including
power entity setup, charger migration, and getting your OCPP credentials.

[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg
[license-shield]: https://img.shields.io/badge/license-MIT-blue.svg
[hacs-shield]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[hacs-url]: https://github.com/hacs/integration
[hacs-badge]: https://my.home-assistant.io/badges/hacs_repository.svg
[hacs-add-url]: https://my.home-assistant.io/redirect/hacs_repository/?owner=thewhalw21&repository=ocpp_charge_proxy&category=integration
[docs]: ocpp_charge_proxy/DOCS.md
[repository-badge]: https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg
[repository-url]: https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fthewhalw21%2Focpp_charge_proxy
