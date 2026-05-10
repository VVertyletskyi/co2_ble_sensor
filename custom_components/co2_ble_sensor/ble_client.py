"""BLE client for CO2 sensor using correct Tuya BLE 3.x protocol."""
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
    DP_CO2, DP_TEMPERATURE, DP_HUMIDITY, DP_BATTERY, DP_CO2_STATE, DP_CO2_ALARM_THRESHOLD,
)
from .tuya_crypto import (
    TuyaBLEProtocol,
    parse_datapoints,
    skip_timestamp,
    unpack_int,
    CMD_DEVICE_INFO, CMD_PAIR, CMD_DEVICE_STATUS,
    CMD_RECEIVE_DP, CMD_RECEIVE_TIME_DP, CMD_RECEIVE_SIGN_DP,
    CMD_RECEIVE_SIGN_TIME_DP, CMD_TIME1_REQ, CMD_TIME2_REQ,
)

_LOGGER = logging.getLogger(__name__)

CONNECT_TIMEOUT = 15
RESPONSE_TIMEOUT = 10


class CO2BLEClient:
    """Manages BLE connection to CO2 sensor with Tuya BLE 3.x protocol."""

    def __init__(
        self,
        ble_device: BLEDevice,
        local_key: str,
        uuid: str,
        connection_mode: str,
        scan_interval: int,
        device_id: str,
        data_callback: Callable[[dict[str, Any]], None],
        auth_error_callback: Callable[[], None] | None = None,
    ) -> None:
        self._device = ble_device
        self._proto = TuyaBLEProtocol(local_key, uuid, device_id)
        self._connection_mode = connection_mode
        self._scan_interval = scan_interval
        self._data_callback = data_callback
        self._auth_error_callback = auth_error_callback
        self._client: BleakClient | None = None
        self._running = False
        self._task: asyncio.Task | None = None
        self._connected = False
        self._last_data: dict[str, Any] = {}

        # Packet reassembly
        self._buf: bytearray | None = None
        self._buf_len: int = 0
        self._buf_pkt: int = 0
        self._buf_flag: int = 0

        # Response futures: seq_num → Future
        self._futures: dict[int, asyncio.Future] = {}

    @property
    def connected(self) -> bool:
        return self._connected

    def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._disconnect()

    async def _run(self) -> None:
        while self._running:
            try:
                await self._connect_and_run()
            except Exception as e:
                _LOGGER.warning("BLE error: %s", e)
            self._connected = False
            if not self._running:
                break
            wait = 5 if self._connection_mode == CONNECTION_MODE_PERSISTENT else self._scan_interval
            await asyncio.sleep(wait)

    async def _connect_and_run(self) -> None:
        _LOGGER.debug("Connecting to %s", self._device.address)
        async with BleakClient(self._device, timeout=CONNECT_TIMEOUT) as client:
            self._client = client
            _LOGGER.debug("Connected to %s", self._device.address)

            await client.start_notify(TUYA_BLE_NOTIFY_UUID, self._notification_handler)

            # Step 1: Device info
            if not await self._send(CMD_DEVICE_INFO, b""):
                _LOGGER.error("Device info request failed")
                return

            if not self._proto.is_ready:
                _LOGGER.error("No session key after device info")
                return

            # Step 2: Pair
            pair_result = await self._send_pair()
            if pair_result == 1:
                _LOGGER.error("Pairing failed — local key may be outdated")
                if self._auth_error_callback:
                    self._auth_error_callback()
                return
            # result 0 or 2 (already paired) = OK

            self._connected = True
            _LOGGER.debug("Paired successfully")

            # Step 3: Request current status
            await self._send(CMD_DEVICE_STATUS, b"")

            if self._connection_mode == CONNECTION_MODE_PERSISTENT:
                while self._running and client.is_connected:
                    await asyncio.sleep(1)
            else:
                await asyncio.sleep(5)

    async def _send(self, code: int, data: bytes) -> bool:
        """Send a packet and wait for response."""
        if not self._client:
            return False
        try:
            packets, seq = self._proto.build_packets(code, data)
        except ValueError as e:
            _LOGGER.error("Cannot build packet: %s", e)
            return False

        future: asyncio.Future = asyncio.Future()
        self._futures[seq] = future

        for pkt in packets:
            await self._client.write_gatt_char(TUYA_BLE_WRITE_UUID, pkt, response=False)

        try:
            await asyncio.wait_for(future, RESPONSE_TIMEOUT)
            return True
        except asyncio.TimeoutError:
            _LOGGER.warning("Timeout waiting for response to cmd=0x%04X", code)
            self._futures.pop(seq, None)
            return False

    async def _send_pair(self) -> int:
        """Send pair request and return result code."""
        if not self._client:
            return -1
        try:
            packets, seq = self._proto.build_packets(CMD_PAIR, self._proto.build_pair_data())
        except ValueError:
            return -1

        future: asyncio.Future = asyncio.Future()
        self._futures[seq] = future

        for pkt in packets:
            await self._client.write_gatt_char(TUYA_BLE_WRITE_UUID, pkt, response=False)

        try:
            result = await asyncio.wait_for(future, RESPONSE_TIMEOUT)
            return result
        except asyncio.TimeoutError:
            self._futures.pop(seq, None)
            return -1

    async def _send_response(self, code: int, data: bytes, resp_to: int) -> None:
        """Send a response packet."""
        if not self._client or not self._client.is_connected:
            return
        try:
            packets, _ = self._proto.build_packets(code, data, response_to=resp_to)
            for pkt in packets:
                await self._client.write_gatt_char(TUYA_BLE_WRITE_UUID, pkt, response=False)
        except Exception as e:
            _LOGGER.debug("Send response error: %s", e)

    async def _disconnect(self) -> None:
        if self._client and self._client.is_connected:
            try:
                await self._client.disconnect()
            except Exception:
                pass
        self._connected = False
        self._client = None

    def _notification_handler(self, sender: Any, data: bytearray) -> None:
        """Handle incoming BLE notifications — reassemble multi-packet messages."""
        pos = 0
        pkt_num, pos = unpack_int(data, pos)
        if pkt_num is None:
            return

        if pkt_num == 0:
            self._buf = bytearray()
            self._buf_len, pos = unpack_int(data, pos)
            if self._buf_len is None:
                return
            # Protocol version byte (skip)
            pos += 1
            self._buf_pkt = 0
            self._buf_flag = 0

        if pkt_num == self._buf_pkt and self._buf is not None:
            self._buf += data[pos:]
            self._buf_pkt += 1

        if self._buf is not None and len(self._buf) >= self._buf_len:
            self._process_packet()

    def _process_packet(self) -> None:
        """Process a complete reassembled packet."""
        if not self._buf:
            return
        buf = bytes(self._buf)
        self._buf = None
        self._buf_pkt = 0

        flag = buf[0]
        parsed = self._proto.parse_packet(buf, flag)
        if not parsed:
            return

        seq     = parsed["seq"]
        resp_to = parsed["resp_to"]
        code    = parsed["code"]
        data    = parsed["data"]

        _LOGGER.debug("Received: seq=%d code=0x%04X resp_to=%d", seq, code, resp_to)
        self._handle(seq, resp_to, code, data)

    def _handle(self, seq: int, resp_to: int, code: int, data: bytes) -> None:
        """Handle decoded command or response."""
        # Resolve futures for responses
        if resp_to != 0:
            future = self._futures.pop(resp_to, None)
            if future and not future.done():
                result = data[0] if data else 0
                # For pair: pass result code; for others: pass 0 (success)
                if code == CMD_PAIR:
                    future.set_result(result if result != 2 else 0)
                else:
                    future.set_result(0)

        if code == CMD_DEVICE_INFO:
            info = self._proto.process_device_info(data)
            _LOGGER.debug("Device info: %s", info)

        elif code == CMD_RECEIVE_DP:
            self._process_dps(data, 0)
            asyncio.create_task(self._send_response(code, b"", seq))

        elif code == CMD_RECEIVE_TIME_DP:
            start = skip_timestamp(data, 0)
            self._process_dps(data, start)
            asyncio.create_task(self._send_response(code, b"", seq))

        elif code == CMD_RECEIVE_SIGN_DP:
            import struct as _struct
            dp_seq = int.from_bytes(data[:2], "big")
            flags  = data[2] if len(data) > 2 else 0
            self._process_dps(data, 3)
            asyncio.create_task(self._send_response(
                code, _struct.pack(">HBB", dp_seq, flags, 0), seq))

        elif code == CMD_RECEIVE_SIGN_TIME_DP:
            import struct as _struct
            dp_seq = int.from_bytes(data[:2], "big")
            flags  = data[2] if len(data) > 2 else 0
            start  = skip_timestamp(data, 3)
            self._process_dps(data, start)
            asyncio.create_task(self._send_response(
                code, _struct.pack(">HBB", dp_seq, flags, 0), seq))

        elif code == CMD_TIME1_REQ:
            asyncio.create_task(self._send_response(
                code, self._proto.build_time1_response(), seq))

        elif code == CMD_TIME2_REQ:
            asyncio.create_task(self._send_response(
                code, self._proto.build_time2_response(), seq))

    async def set_co2_alarm_threshold(self, value: int) -> bool:
        """Send new CO2 alarm threshold to device (DP26)."""
        import struct as _struct
        # DP format: id(1) + type(1) + len(1) + value(4)
        dp_data = _struct.pack(">BBBI", DP_CO2_ALARM_THRESHOLD, 2, 4, value)
        return await self._send(CMD_SEND_DPS, dp_data)

    def _process_dps(self, data: bytes, start: int) -> None:
        """Parse datapoints and call data callback."""
        dps = parse_datapoints(data, start)
        result = {}

        for dp in dps:
            if dp.id == DP_CO2:
                result["co2"] = dp.value
            elif dp.id == DP_TEMPERATURE:
                result["temperature"] = dp.value
            elif dp.id == DP_HUMIDITY:
                result["humidity"] = dp.value
            elif dp.id == DP_BATTERY:
                result["battery"] = dp.value
            elif dp.id == DP_CO2_STATE:
                result["co2_state"] = dp.value
            elif dp.id == DP_CO2_ALARM_THRESHOLD:
                result["co2_alarm_threshold"] = dp.value

        if result:
            self._last_data.update(result)
            _LOGGER.debug("Data: %s", result)
            self._data_callback(self._last_data)
