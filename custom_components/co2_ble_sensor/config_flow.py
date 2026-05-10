"""Config flow for CO2 BLE Sensor."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, OptionsFlow, ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    CONF_ACCESS_ID,
    CONF_ACCESS_SECRET,
    CONF_REGION,
    CONF_CONNECTION_MODE,
    CONF_SCAN_INTERVAL,
    CONNECTION_MODE_PERSISTENT,
    CONNECTION_MODE_SMART,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_CONNECTION_MODE,
    DEFAULT_REGION,
    TUYA_REGIONS,
    TUYA_BLE_SERVICE_UUID,
)
from .tuya_cloud import TuyaCloudClient

_LOGGER = logging.getLogger(__name__)


class CO2BLESensorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle config flow for CO2 BLE Sensor."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}
        self._credentials: dict[str, Any] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle bluetooth discovery."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {"name": discovery_info.name or discovery_info.address}
        return await self.async_step_credentials()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle user initiated flow."""
        return await self.async_step_device()

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle device selection."""
        errors = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            self._discovery_info = self._discovered_devices.get(address)
            if self._discovery_info:
                await self.async_set_unique_id(address, raise_on_progress=False)
                self._abort_if_unique_id_configured()
                return await self.async_step_credentials()
            errors["base"] = "device_not_found"

        # Discover BLE devices
        current_ids = self._async_current_ids()
        for info in async_discovered_service_info(self.hass):
            if info.address not in current_ids:
                if TUYA_BLE_SERVICE_UUID in (info.service_uuids or []):
                    self._discovered_devices[info.address] = info

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema({
                vol.Required(CONF_ADDRESS): vol.In({
                    addr: f"{info.name or addr} ({addr})"
                    for addr, info in self._discovered_devices.items()
                })
            }),
            errors=errors,
        )

    async def async_step_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle Tuya credentials input."""
        errors = {}

        if user_input is not None:
            self._credentials = user_input
            # Verify credentials and get device key
            return await self.async_step_verify()

        return self.async_show_form(
            step_id="credentials",
            data_schema=vol.Schema({
                vol.Required(CONF_REGION, default=DEFAULT_REGION): vol.In(TUYA_REGIONS),
                vol.Required(CONF_ACCESS_ID): str,
                vol.Required(CONF_ACCESS_SECRET): str,
            }),
            errors=errors,
            description_placeholders={
                "device": self._discovery_info.address if self._discovery_info else ""
            },
        )

    async def async_step_verify(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Verify credentials and get device key from Tuya cloud."""
        address = self._discovery_info.address if self._discovery_info else ""

        cloud = TuyaCloudClient(
            access_id=self._credentials[CONF_ACCESS_ID],
            access_secret=self._credentials[CONF_ACCESS_SECRET],
            region=self._credentials.get(CONF_REGION, DEFAULT_REGION),
        )

        device_creds = await cloud.get_device_credentials(address)
        if not device_creds:
            return self.async_show_form(
                step_id="credentials",
                data_schema=vol.Schema({
                    vol.Required(CONF_REGION, default=DEFAULT_REGION): vol.In(TUYA_REGIONS),
                    vol.Required(CONF_ACCESS_ID): str,
                    vol.Required(CONF_ACCESS_SECRET): str,
                }),
                errors={"base": "cannot_connect"},
            )

        return self.async_create_entry(
            title=device_creds.get("name", address),
            data={
                CONF_ADDRESS: address,
                "local_key": device_creds["local_key"],
                "uuid": device_creds["uuid"],
                "device_id": device_creds["device_id"],
                **self._credentials,
            },
            options={
                CONF_CONNECTION_MODE: DEFAULT_CONNECTION_MODE,
                CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return CO2BLEOptionsFlow(config_entry)


class CO2BLEOptionsFlow(OptionsFlow):
    """Handle options flow."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_CONNECTION_MODE,
                    default=self._config_entry.options.get(
                        CONF_CONNECTION_MODE, DEFAULT_CONNECTION_MODE
                    ),
                ): vol.In({
                    CONNECTION_MODE_SMART: "Smart (save battery)",
                    CONNECTION_MODE_PERSISTENT: "Persistent (real-time)",
                }),
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=self._config_entry.options.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=10, max=3600)),
            }),
        )
