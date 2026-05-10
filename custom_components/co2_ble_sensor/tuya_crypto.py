"""Tuya BLE protocol implementation (based on ha_tuya_ble by PlusPlus-ua)."""
from __future__ import annotations

import hashlib
import logging
import secrets
import struct
import time
from dataclasses import dataclass
from typing import Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

_LOGGER = logging.getLogger(__name__)

# Command codes
CMD_DEVICE_INFO   = 0x0000
CMD_PAIR          = 0x0001
CMD_SEND_DPS      = 0x0002
CMD_DEVICE_STATUS = 0x0003
CMD_RECEIVE_DP           = 0x8001
CMD_RECEIVE_TIME_DP      = 0x8003
CMD_RECEIVE_SIGN_DP      = 0x8004
CMD_RECEIVE_SIGN_TIME_DP = 0x8005
CMD_TIME1_REQ            = 0x8011
CMD_TIME2_REQ            = 0x8012

GATT_MTU = 20


def calc_crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte & 255
        for _ in range(8):
            tmp = crc & 1
            crc >>= 1
            if tmp:
                crc ^= 0xA001
    return crc


def pack_int(value: int) -> bytes:
    result = bytearray()
    while True:
        curr = value & 0x7F
        value >>= 7
        if value:
            curr |= 0x80
        result += bytes([curr])
        if not value:
            break
    return bytes(result)


def unpack_int(data: bytes, pos: int) -> tuple[int | None, int]:
    result, offset = 0, 0
    while offset < 5:
        p = pos + offset
        if p >= len(data):
            return None, pos
        b = data[p]
        result |= (b & 0x7F) << (offset * 7)
        offset += 1
        if not (b & 0x80):
            break
    return result, pos + offset


def aes_cbc_encrypt(key: bytes, iv: bytes, data: bytes) -> bytes:
    while len(data) % 16:
        data += b"\x00"
    cipher = Cipher(algorithms.AES(key[:16]), modes.CBC(iv), backend=default_backend())
    enc = cipher.encryptor()
    return enc.update(data) + enc.finalize()


def aes_cbc_decrypt(key: bytes, iv: bytes, data: bytes) -> bytes:
    cipher = Cipher(algorithms.AES(key[:16]), modes.CBC(iv), backend=default_backend())
    dec = cipher.decryptor()
    return dec.update(data) + dec.finalize()


@dataclass
class TuyaDataPoint:
    id: int
    type: int
    value: Any


def parse_datapoints(data: bytes, start: int = 0) -> list[TuyaDataPoint]:
    result = []
    pos = start
    while len(data) - pos >= 3:
        dp_id   = data[pos];     pos += 1
        dp_type = data[pos];     pos += 1
        dp_len  = data[pos];     pos += 1
        if pos + dp_len > len(data):
            break
        raw = data[pos:pos + dp_len]; pos += dp_len

        if dp_type == 1:    # BOOL
            val = bool(raw[0]) if raw else False
        elif dp_type == 2:  # VALUE (signed int)
            val = int.from_bytes(raw, "big", signed=True)
        elif dp_type == 3:  # STRING
            val = raw.decode("utf-8", errors="replace")
        elif dp_type == 4:  # ENUM
            val = int.from_bytes(raw, "big") if raw else 0
        else:               # RAW/BITMAP
            val = raw

        result.append(TuyaDataPoint(id=dp_id, type=dp_type, value=val))
    return result


def skip_timestamp(data: bytes, pos: int) -> int:
    if pos >= len(data):
        return pos
    time_type = data[pos]; pos += 1
    if time_type == 0:    # 13-byte ms string
        pos += 13
    elif time_type == 1:  # 4-byte unix
        pos += 4
    return pos


class TuyaBLEProtocol:
    """Handles Tuya BLE 3.x protocol encryption and packet building."""

    def __init__(self, local_key: str, uuid: str, device_id: str) -> None:
        self._local_key_6 = local_key[:6].encode()
        self._uuid = uuid
        self._device_id = device_id
        self._login_key = hashlib.md5(self._local_key_6).digest()
        self._session_key: bytes | None = None
        self._protocol_version = 3
        self._seq = 1

    @property
    def is_ready(self) -> bool:
        return self._session_key is not None

    def process_device_info(self, data: bytes) -> dict:
        """Parse device info response and compute session key."""
        if len(data) < 12:
            return {}
        srand = data[6:12]
        self._session_key = hashlib.md5(self._local_key_6 + srand).digest()
        self._protocol_version = data[2]
        return {
            "device_version": f"{data[0]}.{data[1]}",
            "protocol_version": f"{data[2]}.{data[3]}",
            "is_bound": data[5] != 0,
        }

    def build_pair_data(self) -> bytes:
        """Build pairing payload: uuid + local_key[:6] + device_id, padded to 44."""
        result = bytearray()
        result += self._uuid.encode()
        result += self._local_key_6
        result += self._device_id.encode()
        while len(result) < 44:
            result += b"\x00"
        return bytes(result[:44])

    def build_time1_response(self) -> bytes:
        ts = int(time.time_ns() / 1_000_000)
        tz = -int(time.timezone / 36)
        return str(ts).encode() + struct.pack(">h", tz)

    def build_time2_response(self) -> bytes:
        t = time.localtime()
        tz = -int(time.timezone / 36)
        return struct.pack(">BBBBBBBh",
            t.tm_year % 100, t.tm_mon, t.tm_mday,
            t.tm_hour, t.tm_min, t.tm_sec, t.tm_wday, tz)

    def build_packets(self, code: int, data: bytes, response_to: int = 0) -> list[bytes]:
        """Build BLE packets for a command."""
        key = self._login_key if code == CMD_DEVICE_INFO else self._session_key
        if key is None:
            raise ValueError("Session key not available")

        seq = self._seq; self._seq += 1
        iv = secrets.token_bytes(16)
        security_flag = b"\x04" if code == CMD_DEVICE_INFO else b"\x05"

        raw = bytearray()
        raw += struct.pack(">IIHH", seq, response_to, code, len(data))
        raw += data
        crc = calc_crc16(raw)
        raw += struct.pack(">H", crc)
        while len(raw) % 16:
            raw += b"\x00"

        encrypted = security_flag + iv + aes_cbc_encrypt(key, iv, bytes(raw))

        packets, packet_num, pos, length = [], 0, 0, len(encrypted)
        while pos < length:
            packet = bytearray(pack_int(packet_num))
            if packet_num == 0:
                packet += pack_int(length)
                packet += bytes([self._protocol_version << 4])
            data_part = encrypted[pos:pos + GATT_MTU - len(packet)]
            packet += data_part
            packets.append(bytes(packet))
            pos += len(data_part)
            packet_num += 1

        return packets, seq

    def parse_packet(self, buf: bytes, flag: int) -> dict | None:
        """Decrypt and parse a complete received packet."""
        key = self._login_key if flag == 4 else self._session_key
        if key is None:
            return None
        try:
            iv = buf[1:17]
            encrypted = buf[17:]
            raw = aes_cbc_decrypt(key, iv, encrypted)
            seq, resp_to, code, length = struct.unpack(">IIHH", raw[:12])
            data = raw[12:12 + length]
            return {"seq": seq, "resp_to": resp_to, "code": code, "data": data}
        except Exception as e:
            _LOGGER.debug("Packet parse error: %s", e)
            return None
