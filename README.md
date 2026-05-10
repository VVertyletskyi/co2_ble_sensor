# CO2 BLE Sensor for Home Assistant

Local Bluetooth integration for Tuya-based CO2 sensors (MOES BSS-X-CO2-U and similar).

## Features

- **100% local** — no cloud needed after initial setup
- **Two connection modes:**
  - **Smart** — connect, read, disconnect (saves battery)
  - **Persistent** — always connected (real-time updates)
- **Auto-discovery** — finds the sensor automatically via BLE
- **Auto key refresh** — updates encryption key if it changes
- **Sensors:** CO2, Temperature, Humidity, Battery, CO2 State

## Supported Devices

- MOES BSS-X-CO2-U
- Any Tuya BLE CO2 sensor with service UUID `0000a201-0000-1000-8000-00805f9b34fb`

## Installation

### Via HACS

1. Add this repository as custom repository in HACS
2. Install "CO2 BLE Sensor"
3. Restart Home Assistant

### Manual

1. Copy `custom_components/co2_ble_sensor` to your HA `custom_components` folder
2. Restart Home Assistant

## Setup

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **CO2 BLE Sensor**
3. Select your device from the list
4. Enter your Tuya IoT Platform credentials:
   - Access ID and Secret from [iot.tuya.com](https://iot.tuya.com)
   - Your Smart Life / MOES app email and password
5. Done! The integration will automatically get the encryption key.

## Getting Tuya Credentials

1. Go to [iot.tuya.com](https://iot.tuya.com)
2. Create a new project (Smart Home, Central Europe Data Center)
3. Link your Smart Life / MOES account
4. Copy Access ID and Access Secret from the project Overview page

## Options

After setup you can configure:
- **Connection mode**: Smart (save battery) or Persistent (real-time)
- **Update interval**: 10-3600 seconds (Smart mode only)
