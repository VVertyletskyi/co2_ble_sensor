"""Tuya BLE encryption and decryption."""
from __future__ import annotations

import hashlib
import logging
import struct
import time
from dataclasses import dataclass
from typing import Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

_LOGGER = logging.getLogger(__name__)

# Tuya BLE packet constants
TUYA_BLE_FRAME_MAGIC = 0x000055AA
TUYA_BLE_FRAME_TAIL = 0x00AA55
TUYA_BLE_PROTOCOL_VERSION = 0x03

# Commands
CMD_PAIR_REQ = 0x00
CMD_PAIR_RESP = 0x01
CMD_SESS_KEY_NEG_START = 0x05
CMD_SESS_KEY_NEG_RES = 0x06
CMD_SESS_KEY_NEG_FINISH = 0x07
CMD_BOUND_REQ = 0x08
CMD_BOUND_RESP = 0x09
CMD_DEVICE_INFO_REQ = 0x0E
CMD_DEVICE_INFO_RESP = 0x0F
CMD_DATA_REPORT = 0x22
CMD_DATA_QUERY = 0x24
CMD_STATUS_REPORT = 0x22


@dataclass
class TuyaBLEPacket:
    """Tuya BLE packet."""
    cmd: int
    data: bytes
    seq: int = 0


class TuyaBLECrypto:
    """Handles Tuya BLE encryption."""

    def __init__(self, local_key: str, uuid: str) -> None:
        self._local_key = local_key.encode()
        self._uuid = uuid.encode()
        self._session_key: bytes | None = None
        self._seq = 0

    def _get_key(self) -> bytes:
        """Get encryption key."""
        if self._session_key:
            return self._session_key
        return self._local_key[:16].ljust(16, b'\0')

    def _encrypt(self, data: bytes, key: bytes) -> bytes:
        """Encrypt data with AES-128-ECB."""
        remainder = len(data) % 16
        padded = data + b'\0' * (16 - remainder) if remainder else data + b'\0' * 16
        cipher = Cipher(
            algorithms.AES(key[:16]),
            modes.ECB(),
            backend=default_backend()
        )
        encryptor = cipher.encryptor()
        return encryptor.update(padded) + encryptor.finalize()

    def _decrypt(self, data: bytes, key: bytes) -> bytes:
        """Decrypt data with AES-128-ECB."""
        cipher = Cipher(
            algorithms.AES(key[:16]),
            modes.ECB(),
            backend=default_backend()
        )
        decryptor = cipher.decryptor()
        return decryptor.update(data) + decryptor.finalize()

    def build_packet(self, cmd: int, data: bytes) -> bytes:
        """Build encrypted Tuya BLE packet."""
        self._seq += 1
        seq = self._seq

        # Build inner data
        inner = struct.pack(">I", seq) + struct.pack(">H", cmd) + struct.pack(">H", len(data)) + data

        # Encrypt
        key = self._get_key()
        encrypted = self._encrypt(inner, key)

        # Build frame
        frame = struct.pack(">I", TUYA_BLE_FRAME_MAGIC)
        frame += struct.pack(">B", TUYA_BLE_PROTOCOL_VERSION)
        frame += struct.pack(">B", 0x00)  # encrypt type
        frame += struct.pack(">H", len(encrypted))
        frame += encrypted

        # CRC
        crc = sum(frame[4:]) & 0xFF
        frame += struct.pack(">B", crc)
        frame += struct.pack(">H", TUYA_BLE_FRAME_TAIL)

        return frame

    def parse_packet(self, data: bytes) -> TuyaBLEPacket | None:
        """Parse and decrypt incoming Tuya BLE packet."""
        try:
            if len(data) < 12:
                return None

            # Check magic
            magic = struct.unpack(">I", data[:4])[0]
            if magic != TUYA_BLE_FRAME_MAGIC:
                return None

            length = struct.unpack(">H", data[6:8])[0]
            encrypted = data[8:8 + length]

            key = self._get_key()
            decrypted = self._decrypt(encrypted, key)

            seq = struct.unpack(">I", decrypted[:4])[0]
            cmd = struct.unpack(">H", decrypted[4:6])[0]
            data_len = struct.unpack(">H", decrypted[6:8])[0]
            payload = decrypted[8:8 + data_len]

            return TuyaBLEPacket(cmd=cmd, data=payload, seq=seq)
        except Exception as e:
            _LOGGER.debug("Failed to parse packet: %s", e)
            return None

    def build_query_packet(self) -> bytes:
        """Build data query packet."""
        return self.build_packet(CMD_DATA_QUERY, b'')

    def set_session_key(self, key: bytes) -> None:
        """Set negotiated session key."""
        self._session_key = key


def parse_datapoints(data: bytes) -> dict[int, Any]:
    """Parse Tuya datapoints from payload."""
    result = {}
    offset = 0

    while offset + 4 <= len(data):
        dp_id = data[offset]
        dp_type = data[offset + 1]
        dp_len = struct.unpack(">H", data[offset + 2:offset + 4])[0]
        offset += 4

        if offset + dp_len > len(data):
            break

        dp_data = data[offset:offset + dp_len]
        offset += dp_len

        if dp_type == 0x01:  # boolean
            result[dp_id] = bool(dp_data[0])
        elif dp_type == 0x02:  # integer
            result[dp_id] = int.from_bytes(dp_data, "big", signed=True)
        elif dp_type == 0x03:  # string
            result[dp_id] = dp_data.decode("utf-8", errors="ignore")
        elif dp_type == 0x04:  # enum
            result[dp_id] = dp_data.decode("utf-8", errors="ignore")
        elif dp_type == 0x05:  # raw
            result[dp_id] = dp_data.hex()

    return result
