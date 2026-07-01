# Denkirs for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
[![CI](https://github.com/Wayfarer545/denkirs/actions/workflows/ci.yml/badge.svg)](https://github.com/Wayfarer545/denkirs/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

Local control of **Denkirs** smart track lighting in Home Assistant — no cloud at
runtime, no vendor account, no polling of anyone's servers.

Denkirs SMART fixtures are Tuya BLE-mesh nodes that sit behind a Wi-Fi gateway.
This integration talks to the gateway over the local Tuya LAN protocol and
addresses each fixture by its mesh id, so brightness and colour-temperature
control stay entirely on your network.

## Features

- **Fully local.** Control runs over the LAN; the gateway never needs the
  internet once it is set up.
- **Tunable-white lights.** On/off, brightness and colour temperature, exposed
  as native Home Assistant `light` entities with proper Kelvin support.
- **One device per fixture.** Every fixture is its own device, linked to the
  gateway, so dashboards and automations stay tidy.
- **Resilient polling.** A fixture that stops answering goes unavailable on its
  own without taking its neighbours down.
- **Guided setup.** A local config flow validates the connection before it
  creates the entry, and an options flow tunes the polling interval.

## How it works

```
Home Assistant ── Tuya LAN (:6668) ──> Wi-Fi gateway ── BLE mesh ──> fixtures
```

The gateway is the only device Home Assistant talks to. Each fixture is a mesh
node reached through the gateway by its mesh id (`cid`). The integration keeps a
single serialised connection to the gateway and applies changes atomically so
fixtures never flicker between intermediate states.

## Requirements

- Home Assistant 2026.6 or newer.
- The gateway joined to the same LAN as Home Assistant.
- The gateway's `device id` and `local key`, and each fixture's `device id` and
  mesh `cid` (see [Finding your credentials](#finding-your-credentials)).

## Installation

### HACS (recommended)

1. In HACS, open the menu → **Custom repositories**.
2. Add `https://github.com/Wayfarer545/denkirs` as an **Integration**.
3. Install **Denkirs** and restart Home Assistant.

### Manual

Copy `custom_components/denkirs` into your Home Assistant `config/custom_components`
directory and restart.

## Configuration

Go to **Settings → Devices & Services → Add Integration → Denkirs**.

1. **Gateway** — enter the gateway's host (IP), device id and local key.
2. **Fixtures** — add each fixture: a friendly name, its device id, its mesh
   `cid`, and optionally the model. Tick *Add another fixture* to keep going.

Before the entry is created the integration polls the first fixture to confirm
the host and key are correct. If it fails you are returned to the gateway step
with your details preserved.

### Options

**Configure** on the integration lets you change the polling interval
(5–600 seconds, default 30).

## Entities

Each fixture becomes one `light` entity supporting:

| Capability        | Datapoint | Range (device)     |
| ----------------- | --------- | ------------------ |
| On / off          | `1`       | boolean            |
| Brightness        | `3`       | 10–1000            |
| Colour temperature| `4`       | 0–1000 (2700–6500 K)|

## Finding your credentials

Local keys are issued by Tuya. The usual one-time route is the free
[Tuya IoT Platform](https://iot.tuya.com) with the
[`tinytuya` wizard](https://github.com/jasonacox/tinytuya#setup-wizard), which
lists every device with its `device id`, `local key` and, for fixtures behind a
gateway, the mesh `cid`. This is only needed once during setup; the gateway does
not use the cloud afterwards.

## Running without internet

Because control is entirely local, you can block the gateway's outbound internet
access on your router and everything keeps working. Note that Tuya gateways tend
to use hard-coded public DNS, so a DNS-level block is not enough — block the
gateway's WAN access at the router (for example by its MAC address).

## Troubleshooting

- **Cannot connect during setup** — check the host and local key. The local key
  changes if the device is reset or re-paired; re-read it if in doubt.
- **A fixture is unavailable** — verify its mesh `cid`. A wrong `cid` produces no
  error but the fixture never reports state.
- **Download diagnostics** from the integration for a redacted snapshot of the
  configuration and current fixture state.

## Development

```bash
pip install -r requirements_test.txt
ruff check . && ruff format --check .
mypy custom_components/denkirs
pytest
```

The test suite runs against a mocked transport and Home Assistant's test
harness; no hardware is required.

## Branding

The Denkirs icon ships with the integration under `custom_components/denkirs/brand/`.
Home Assistant serves it directly — local brand images take priority over the
brands CDN since 2026.3 — so it appears in the UI with no submission to the
[home-assistant/brands](https://github.com/home-assistant/brands) repository.

## License

Released under the [Apache License 2.0](LICENSE).
