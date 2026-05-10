# CO2 BLE Sensor for Home Assistant

Local Bluetooth integration for Tuya-based CO2 sensors (MOES BSS-X-CO2-U and similar).

## Features

- **100% local** — no cloud needed after initial setup
- **Auto-discovery** — finds the sensor automatically via BLE
- **Sensors:** CO2 (ppm), Temperature (°C), Humidity (%), Battery (%), CO2 State
- **Control:** CO2 alarm threshold (set the ppm level at which the sensor beeps)
- **Smart connection mode** — connect, read, disconnect (saves battery)
- **Persistent connection mode** — always connected (real-time updates)
- **Auto key refresh notification** — alerts you if the encryption key needs updating

## Supported Devices

- MOES BSS-X-CO2-U
- Any Tuya BLE CO2 sensor with service UUID `0000a201-0000-1000-8000-00805f9b34fb`

## Requirements

- Home Assistant 2023.x or newer
- Bluetooth adapter on your HA host
- Tuya IoT Platform account ([iot.tuya.com](https://iot.tuya.com)) — needed only once to get device credentials

## Installation

### Via HACS

1. Add this repository as a custom repository in HACS
2. Install **CO2 BLE Sensor**
3. Restart Home Assistant

### Manual

1. Copy `custom_components/co2_ble_sensor` to your HA `custom_components` folder
2. Restart Home Assistant

## Setup

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **CO2 BLE Sensor**
3. Select your device from the discovered list
4. Enter your Tuya IoT Platform credentials:
   - Region (Europe for Ukraine/EU)
   - Access ID and Secret from [iot.tuya.com](https://iot.tuya.com)
5. Done! The integration will automatically get the encryption key.

## Getting Tuya Credentials

1. Go to [iot.tuya.com](https://iot.tuya.com) and create an account
2. Create a new project: **Cloud → Development → Create Cloud Project**
   - Choose **Smart Home** and **Central Europe Data Center** (for EU)
3. In your project go to **Devices → Link App Account** and link your Smart Life account
4. Copy **Access ID** and **Access Secret** from the project Overview page

## Troubleshooting

### "Encryption key outdated" notification

If you see a notification saying the key is outdated:
1. Open the **Smart Life** or **MOES** app
2. Make sure your CO2 sensor shows as **online**
3. Remove the integration and add it again — it will fetch a fresh key

### Device not found

- Make sure the sensor is powered on and within BLE range (~10m)
- Check that your HA host has a working Bluetooth adapter

## Entities

| Entity | Type | Description |
|--------|------|-------------|
| CO2 | Sensor | CO2 concentration in ppm |
| Temperature | Sensor | Temperature in °C |
| Humidity | Sensor | Relative humidity in % |
| Battery | Sensor | Battery level in % |
| CO2 State | Sensor | CO2 level status |
| CO2 Alarm Threshold | Number | PPM level that triggers the beep alarm |

## Connection Modes

After setup you can configure (Settings → Devices & Services → CO2 BLE Sensor → Configure):

- **Smart** (default) — connects, reads data, disconnects. Saves battery. Update interval configurable (10–3600 sec).
- **Persistent** — stays connected for real-time updates.
