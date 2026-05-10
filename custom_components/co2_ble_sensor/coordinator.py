"""Coordinator for CO2 BLE Sensor."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_ble_device_from_address,
)

from .const import DOMAIN, SIGNAL_UPDATE
from .ble_client import CO2BLEClient

_LOGGER = logging.getLogger(__name__)


class CO2BLECoordinator:
    """Coordinates data from CO2 BLE sensor."""

    def __init__(
        self,
        hass: HomeAssistant,
        address: str,
        local_key: str,
        uuid: str,
        device_id: str,
        name: str,
        connection_mode: str,
        scan_interval: int,
    ) -> None:
        self.hass = hass
        self.address = address
        self.device_id = device_id
        self.name = name
        self.data: dict[str, Any] = {}
        self._local_key = local_key
        self._uuid = uuid
        self._connection_mode = connection_mode
        self._scan_interval = scan_interval
        self._client: CO2BLEClient | None = None

    @property
    def connected(self) -> bool:
        return self._client is not None and self._client.connected

    async def async_start(self) -> None:
        """Start the coordinator."""
        ble_device = async_ble_device_from_address(self.hass, self.address)
        if not ble_device:
            _LOGGER.error("BLE device %s not found", self.address)
            return

        self._client = CO2BLEClient(
            ble_device=ble_device,
            local_key=self._local_key,
            uuid=self._uuid,
            connection_mode=self._connection_mode,
            scan_interval=self._scan_interval,
            data_callback=self._on_data,
        )
        self._client.start()

    async def async_stop(self) -> None:
        """Stop the coordinator."""
        if self._client:
            await self._client.stop()
            self._client = None

    @callback
    def _on_data(self, data: dict[str, Any]) -> None:
        """Handle new data from sensor."""
        self.data = data
        async_dispatcher_send(self.hass, f"{SIGNAL_UPDATE}_{self.address}")
