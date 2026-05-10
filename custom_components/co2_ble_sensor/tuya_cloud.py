"""Tuya Cloud API client for getting device credentials."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any

import aiohttp

from .const import TUYA_API_URL, TUYA_API_TOKEN_URL, TUYA_API_DEVICES_URL

_LOGGER = logging.getLogger(__name__)


class TuyaCloudClient:
    """Client for Tuya Cloud API."""

    def __init__(
        self,
        access_id: str,
        access_secret: str,
        username: str,
        password: str,
        country_code: str = "380",
    ) -> None:
        self._access_id = access_id
        self._access_secret = access_secret
        self._username = username
        self._password = password
        self._country_code = country_code
        self._token: str | None = None
        self._token_expiry: float = 0

    def _sign(self, method: str, path: str, body: str = "", token: str = "") -> dict:
        """Generate Tuya API signature."""
        t = str(int(time.time() * 1000))
        body_hash = hashlib.sha256(body.encode()).hexdigest()
        str_to_sign = "\n".join([method, body_hash, "", path])
        message = self._access_id + token + t + str_to_sign
        sign = hmac.new(
            self._access_secret.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest().upper()
        return {
            "client_id": self._access_id,
            "sign": sign,
            "t": t,
            "sign_method": "HMAC-SHA256",
            "access_token": token,
        }

    async def _get_token(self, session: aiohttp.ClientSession) -> str | None:
        """Get or refresh access token."""
        if self._token and time.time() < self._token_expiry:
            return self._token

        headers = self._sign("GET", TUYA_API_TOKEN_URL)
        try:
            async with session.get(
                f"{TUYA_API_URL}{TUYA_API_TOKEN_URL}",
                headers=headers,
            ) as resp:
                data = await resp.json()
                if data.get("success"):
                    result = data["result"]
                    self._token = result["access_token"]
                    self._token_expiry = time.time() + result.get("expire_time", 7200)
                    return self._token
                _LOGGER.error("Failed to get Tuya token: %s", data)
        except Exception as e:
            _LOGGER.error("Error getting Tuya token: %s", e)
        return None

    async def get_device_credentials(
        self, mac_address: str
    ) -> dict[str, Any] | None:
        """Get device credentials by MAC address."""
        async with aiohttp.ClientSession() as session:
            token = await self._get_token(session)
            if not token:
                return None

            # Search devices by username
            path = f"/v1.0/users/{self._username}/devices"
            headers = self._sign("GET", path, token=token)
            headers["Content-Type"] = "application/json"

            try:
                async with session.get(
                    f"{TUYA_API_URL}{path}",
                    headers=headers,
                ) as resp:
                    data = await resp.json()
                    if not data.get("success"):
                        _LOGGER.error("Failed to get devices: %s", data)
                        return None

                    devices = data.get("result", [])
                    mac_clean = mac_address.replace(":", "").upper()

                    for device in devices:
                        device_id = device.get("id")
                        if not device_id:
                            continue

                        # Get factory info (MAC address)
                        fi_path = f"/v1.0/iot-03/devices/factory-infos?device_ids={device_id}"
                        fi_headers = self._sign("GET", fi_path, token=token)
                        async with session.get(
                            f"{TUYA_API_URL}{fi_path}",
                            headers=fi_headers,
                        ) as fi_resp:
                            fi_data = await fi_resp.json()
                            if fi_data.get("success"):
                                result = fi_data.get("result", [])
                                if result and result[0].get("mac", "").upper() == mac_clean:
                                    return {
                                        "device_id": device_id,
                                        "local_key": device.get("local_key"),
                                        "uuid": device.get("uuid"),
                                        "name": device.get("name"),
                                        "product_id": device.get("product_id"),
                                    }
            except Exception as e:
                _LOGGER.error("Error getting device credentials: %s", e)
        return None

    async def get_device_by_id(self, device_id: str) -> dict[str, Any] | None:
        """Get device details by device ID."""
        async with aiohttp.ClientSession() as session:
            token = await self._get_token(session)
            if not token:
                return None

            path = TUYA_API_DEVICES_URL.format(device_id=device_id)
            headers = self._sign("GET", path, token=token)

            try:
                async with session.get(
                    f"{TUYA_API_URL}{path}",
                    headers=headers,
                ) as resp:
                    data = await resp.json()
                    if data.get("success"):
                        return data.get("result")
                    _LOGGER.error("Failed to get device: %s", data)
            except Exception as e:
                _LOGGER.error("Error getting device: %s", e)
        return None
