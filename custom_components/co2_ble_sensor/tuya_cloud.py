"""Tuya Cloud API client for getting device credentials."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any

import aiohttp

from .const import TUYA_API_TOKEN_URL, TUYA_API_DEVICES_URL, TUYA_REGION_URLS, DEFAULT_REGION

_LOGGER = logging.getLogger(__name__)


class TuyaCloudClient:
    """Client for Tuya Cloud API."""

    def __init__(
        self,
        access_id: str,
        access_secret: str,
        username: str,
        password: str,
        region: str = DEFAULT_REGION,
    ) -> None:
        self._access_id = access_id
        self._access_secret = access_secret
        self._username = username
        self._password = password
        self._api_url = TUYA_REGION_URLS.get(region, TUYA_REGION_URLS[DEFAULT_REGION])
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
                f"{self._api_url}{TUYA_API_TOKEN_URL}",
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

    async def _get_user_uid(self, session: aiohttp.ClientSession, token: str) -> str | None:
        """Get user UID by logging in with username/password."""
        path = "/v1.0/iot-01/associated-users/actions/login"
        # Tuya requires MD5 of password
        password_md5 = hashlib.md5(self._password.encode()).hexdigest()
        body = json.dumps({
            "username": self._username,
            "password": password_md5,
            "schema": "smartlife",
        })
        headers = self._sign("POST", path, body=body, token=token)
        headers["Content-Type"] = "application/json"

        try:
            async with session.post(
                f"{self._api_url}{path}",
                headers=headers,
                data=body,
            ) as resp:
                data = await resp.json()
                if data.get("success"):
                    uid = data.get("result", {}).get("uid")
                    _LOGGER.debug("Got user UID: %s", uid)
                    return uid
                _LOGGER.error("Failed to get user UID: %s", data)
        except Exception as e:
            _LOGGER.error("Error getting user UID: %s", e)
        return None

    async def get_device_credentials(
        self, mac_address: str
    ) -> dict[str, Any] | None:
        """Get device credentials by MAC address."""
        async with aiohttp.ClientSession() as session:
            token = await self._get_token(session)
            if not token:
                return None

            # Step 1: get user UID via login
            uid = await self._get_user_uid(session, token)
            if not uid:
                _LOGGER.error("Could not get user UID — check username/password/country_code")
                return None

            # Step 2: get devices for this user
            path = f"/v1.0/users/{uid}/devices"
            headers = self._sign("GET", path, token=token)
            headers["Content-Type"] = "application/json"

            try:
                async with session.get(
                    f"{self._api_url}{path}",
                    headers=headers,
                ) as resp:
                    data = await resp.json()
                    if not data.get("success"):
                        _LOGGER.error("Failed to get devices: %s", data)
                        return None

                    devices = data.get("result", [])
                    mac_clean = mac_address.replace(":", "").upper()
                    _LOGGER.debug("Found %d devices for user", len(devices))

                    for device in devices:
                        device_id = device.get("id")
                        if not device_id:
                            continue

                        # Get factory info to match by MAC
                        fi_path = f"/v1.0/iot-03/devices/factory-infos?device_ids={device_id}"
                        fi_headers = self._sign("GET", fi_path, token=token)
                        async with session.get(
                            f"{self._api_url}{fi_path}",
                            headers=fi_headers,
                        ) as fi_resp:
                            fi_data = await fi_resp.json()
                            if fi_data.get("success"):
                                result = fi_data.get("result", [])
                                if result and result[0].get("mac", "").upper() == mac_clean:
                                    _LOGGER.debug("Found device: %s", device_id)
                                    return {
                                        "device_id": device_id,
                                        "local_key": device.get("local_key"),
                                        "uuid": device.get("uuid"),
                                        "name": device.get("name"),
                                        "product_id": device.get("product_id"),
                                    }

                _LOGGER.error("Device with MAC %s not found among %d devices", mac_address, len(devices))
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
                    f"{self._api_url}{path}",
                    headers=headers,
                ) as resp:
                    data = await resp.json()
                    if data.get("success"):
                        return data.get("result")
                    _LOGGER.error("Failed to get device: %s", data)
            except Exception as e:
                _LOGGER.error("Error getting device: %s", e)
        return None
