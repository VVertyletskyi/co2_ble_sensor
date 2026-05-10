"""Constants for CO2 BLE Sensor integration."""
from __future__ import annotations
from typing import Final

DOMAIN: Final = "co2_ble_sensor"

# Config keys
CONF_ACCESS_ID: Final = "access_id"
CONF_ACCESS_SECRET: Final = "access_secret"
CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
CONF_COUNTRY_CODE: Final = "country_code"
CONF_CONNECTION_MODE: Final = "connection_mode"
CONF_SCAN_INTERVAL: Final = "scan_interval"

# Connection modes
CONNECTION_MODE_PERSISTENT: Final = "persistent"
CONNECTION_MODE_SMART: Final = "smart"

# Default values
DEFAULT_SCAN_INTERVAL: Final = 60  # seconds
DEFAULT_CONNECTION_MODE: Final = CONNECTION_MODE_SMART

# Tuya BLE
TUYA_BLE_SERVICE_UUID: Final = "0000a201-0000-1000-8000-00805f9b34fb"
TUYA_BLE_WRITE_UUID: Final = "00002b11-0000-1000-8000-00805f9b34fb"
TUYA_BLE_NOTIFY_UUID: Final = "00002b10-0000-1000-8000-00805f9b34fb"

# Tuya API
TUYA_API_DEVICES_URL: Final = "/v1.0/devices/{device_id}"
TUYA_API_TOKEN_URL: Final = "/v1.0/token?grant_type=1"

CONF_REGION: Final = "region"
TUYA_REGIONS: Final = {
    "eu": "Europe (openapi.tuyaeu.com)",
    "us": "America (openapi.tuyaus.com)",
    "cn": "China (openapi.tuyacn.com)",
    "in": "India (openapi.tuyain.com)",
}
TUYA_REGION_URLS: Final = {
    "eu": "https://openapi.tuyaeu.com",
    "us": "https://openapi.tuyaus.com",
    "cn": "https://openapi.tuyacn.com",
    "in": "https://openapi.tuyain.com",
}
DEFAULT_REGION: Final = "eu"

# Sensor data points
DP_CO2: Final = 2
DP_TEMPERATURE: Final = 18
DP_HUMIDITY: Final = 19
DP_BATTERY: Final = 15
DP_CO2_STATE: Final = 1
DP_CO2_ALARM_THRESHOLD: Final = 26

# Update signals
SIGNAL_UPDATE = f"{DOMAIN}_update"
