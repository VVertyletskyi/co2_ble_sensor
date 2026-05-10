"""BLE client for CO2 sensor."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from bleak import BleakClient, BleakError
from bleak.backends.device import BLEDevice

from .const import (
    TUYA_BLE_NOTIFY_UUID,
    TUYA_BLE_WRITE_UUID,
    CONNECTION_MODE_PERSISTENT,
    DP_CO2,
    DP_TEMPERATURE,
    DP_HUMIDITY,
    DP_BATTERY,
    DP_CO2_STATE,
)
from .tuya_crypto import TuyaBLECrypto, parse_datapoints, CMD_DATA_REPORT, CMD_STATUS_REPORT

_LOGGER = logging.getLogger(__name__)

CONNECT_TIMEOUT = 10
READ_TIMEOUT = 5


class CO2BLEClient:
    """Manages BLE connection to CO2 sensor."""

    def __init__(
        self,
        ble_device: BLEDevice,
        local_key: str,
        uuid: str,
        connection_mode: str,
        scan_interval: int,
        data_callback: Callable[[dict[str, Any]], None],
    ) -> None:
        self._device = ble_device
        self._crypto = TuyaBLECrypto(local_key, uuid)
        self._connection_mode = connection_mode
        self._scan_interval = scan_interval
        self._data_callback = data_callback
        self._client: BleakClient | None = None
        self._running = False
        self._task: asyncio.Task | None = None
        self._buffer = bytearray()
        self._last_data: dict[str, Any] = {}
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def last_data(self) -> dict[str, Any]:
        return self._last_data

    def start(self) -> None:
        """Start the BLE client loop."""
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Stop the BLE client loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._disconnect()

    async def _run(self) -> None:
        """Main loop."""
        while self._running:
            try:
                await self._connect_and_read()
            except Exception as e:
                _LOGGER.error("BLE error: %s", e)
                self._connected = False

            if not self._running:
                break

            if self._connection_mode == CONNECTION_MODE_PERSISTENT:
                # In persistent mode reconnect immediately
                await asyncio.sleep(5)
            else:
                # In smart mode wait for scan interval
                await asyncio.sleep(self._scan_interval)

    async def _connect_and_read(self) -> None:
        """Connect to device and read data."""
        _LOGGER.debug("Connecting to %s", self._device.address)

        try:
            async with BleakClient(
                self._device,
                timeout=CONNECT_TIMEOUT,
            ) as client:
                self._client = client
                self._connected = True
                _LOGGER.debug("Connected to %s", self._device.address)

                # Subscribe to notifications
                await client.start_notify(
                    TUYA_BLE_NOTIFY_UUID,
                    self._notification_handler,
                )

                # Request data
                query = self._crypto.build_query_packet()
                await client.write_gatt_char(
                    TUYA_BLE_WRITE_UUID,
                    query,
                    response=True,
                )

                if self._connection_mode == CONNECTION_MODE_PERSISTENT:
                    # Stay connected and keep receiving notifications
                    while self._running and client.is_connected:
                        await asyncio.sleep(1)
                else:
                    # Wait for response then disconnect
                    await asyncio.sleep(READ_TIMEOUT)

        except BleakError as e:
            _LOGGER.warning("BLE connection error: %s", e)
        except asyncio.TimeoutError:
            _LOGGER.warning("BLE connection timeout")
        finally:
            self._connected = False
            self._client = None

    async def _disconnect(self) -> None:
        """Disconnect from device."""
        if self._client and self._client.is_connected:
            try:
                await self._client.disconnect()
            except Exception:
                pass
        self._connected = False

    def _notification_handler(self, sender: Any, data: bytearray) -> None:
        """Handle incoming BLE notifications."""
        self._buffer.extend(data)
        self._process_buffer()

    def _process_buffer(self) -> None:
        """Process buffered data."""
        while len(self._buffer) >= 8:
            # Look for frame magic
            if self._buffer[:4] != b'\x00\x00\x55\xAA':
                self._buffer = self._buffer[1:]
                continue

            packet = self._crypto.parse_packet(bytes(self._buffer))
            if packet is None:
                self._buffer = self._buffer[1:]
                continue

            self._buffer.clear()

            if packet.cmd in (CMD_DATA_REPORT, CMD_STATUS_REPORT):
                datapoints = parse_datapoints(packet.data)
                if datapoints:
                    self._process_datapoints(datapoints)
            break

    def _process_datapoints(self, datapoints: dict[int, Any]) -> None:
        """Process received datapoints."""
        data = {}

        if DP_CO2 in datapoints:
            data["co2"] = datapoints[DP_CO2]
        if DP_TEMPERATURE in datapoints:
            data["temperature"] = datapoints[DP_TEMPERATURE] / 10.0
        if DP_HUMIDITY in datapoints:
            data["humidity"] = datapoints[DP_HUMIDITY] / 10.0
        if DP_BATTERY in datapoints:
            data["battery"] = datapoints[DP_BATTERY]
        if DP_CO2_STATE in datapoints:
            data["co2_state"] = datapoints[DP_CO2_STATE]

        if data:
            self._last_data.update(data)
            _LOGGER.debug("Received data: %s", data)
            self._data_callback(self._last_data)
