# Qubo Smart Home — Home Assistant Integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![Version](https://img.shields.io/badge/version-0.5.1-blue.svg)](https://github.com/G-Aman/ha-qubo/releases)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-green.svg)](https://www.home-assistant.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> Control your Qubo smart devices from Home Assistant — lights, plugs, and more.

---

## Supported Devices

### Smart Bulb 9W (HLB01 / HLB06)

Full lighting control with color picker, brightness slider, and preset scenes.

- 💡 On/Off
- 🔆 Brightness (0–100%)
- 🎨 RGB Color (full color picker)
- 🌡️ Color Temperature (warm ↔ cool, 2000K–6535K)
- ✨ 6 Preset Effects (Green, Blue, Red, Warm White, Natural White, Cool White)
- ⏱️ Auto-Off Timer (0–1440 min slider)
- 🎛️ Color Mode Select (White / Color)
- 📡 WiFi Diagnostics (SSID, IP, signal)
- 🔔 Firmware Update Detection
- 🟢 Online Status

### Smart Plug 10A

Outlet control with real-time energy monitoring.

- 🔌 On/Off
- ⚡ Power (W), Voltage (V), Current (mA)
- 📊 Energy Consumption (kWh)
- ⏱️ Usage Duration
- 🔄 Refresh Metering Button
- 📡 WiFi Diagnostics (SSID, IP, signal)
- 🔔 Firmware Update Detection
- 🟢 Online Status

### Camera

Not yet supported — stub ready for future development.

---

## Installation

### HACS (Recommended)

1. Open **HACS** → **Integrations** → ⋮ → **Custom repositories**
2. Add: `https://github.com/G-Aman/ha-qubo` (Category: Integration)
3. Install → Restart Home Assistant

### Manual

1. Copy `custom_components/qubo/` into your HA `config/custom_components/`
2. Restart Home Assistant
3. **Settings** → **Devices & Services** → **+ Add Integration** → **Qubo Smart Home**

---

## Setup

No YAML needed — everything is configured through the UI.

1. Enter your Qubo account email and password
2. Select your device (if you have multiple)
3. Done — entities appear automatically

Add each device as a separate integration entry.

---

## Upgrading from v0.4.x

If you had the older plug-only version installed:

1. Remove the existing config entry (**Settings** → **Devices & Services** → **Qubo** → **Delete**)
2. Update via HACS (or manually replace files)
3. Restart Home Assistant
4. Re-add the integration

The config entry format changed in v0.5.x — old entries are not compatible.

---

## Troubleshooting

**Can't connect?** Check that your HA instance can reach `mqtt.platform.quboworld.com:8883` and your credentials are correct.

**Device offline?** Make sure the device is powered on and connected to WiFi. Allow a few minutes for heartbeat detection.

**No metering data?** Click the **Refresh Metering** button. Data updates periodically.

**Changed password?** Remove and re-add the integration.

---

## License

MIT — see [LICENSE](LICENSE).

Qubo is a product of **Hero Electronix**. This integration is not affiliated with or endorsed by Hero Electronix.
