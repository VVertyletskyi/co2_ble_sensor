"""Coordinator for CO2 BLE Sensor."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.components.bluetooth import async_ble_device_from_address
from homeassistant.components.persistent_notification import async_create, async_dismiss

from .const import DOMAIN, SIGNAL_UPDATE
from .ble_client import CO2BLEClient

_LOGGER = logging.getLogger(__name__)

NOTIFICATION_ID = f"{DOMAIN}_key_expired"
NOTIFICATION_TITLE = "CO2 BLE Sensor — Ключ шифрування застарів"
NOTIFICATION_MESSAGE = (
    "Датчик **{name}** відхиляє з'єднання. "
    "Ключ шифрування міг оновитись.\n\n"
    "**Що зробити:**\n"
    "1. Відкрийте додаток **Smart Life** або **MOES** та переконайтесь що датчик онлайн\n"
    "2. Видаліть цю інтеграцію (**Налаштування → Пристрої та сервіси → CO2 BLE Sensor → Видалити**)\n"
    "3. Додайте інтеграцію знову — вона автоматично отримає свіжий ключ з Tuya cloud\n\n"
    "_Це трапляється коли пристрій перепідключається до Smart Life після скидання або оновлення._"
)


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
            device_id=self.device_id,
            scan_interval=self._scan_interval,
            data_callback=self._on_data,
            auth_error_callback=self._on_auth_error,
        )
        self._client.start()

    async def async_stop(self) -> None:
        """Stop the coordinator."""
        if self._client:
            await self._client.stop()
            self._client = None
        async_dismiss(self.hass, NOTIFICATION_ID)

    @callback
    def _on_data(self, data: dict[str, Any]) -> None:
        """Handle new data from sensor."""
        self.data = data
        # Dismiss notification if we got data successfully
        async_dismiss(self.hass, NOTIFICATION_ID)
        async_dispatcher_send(self.hass, f"{SIGNAL_UPDATE}_{self.address}")

    @callback
    def _on_auth_error(self) -> None:
        """Handle BLE authentication failure — local key is likely outdated."""
        _LOGGER.error(
            "BLE auth failed for %s (%s) — local key may be outdated",
            self.name, self.address
        )
        async_create(
            self.hass,
            NOTIFICATION_MESSAGE.format(name=self.name),
            title=NOTIFICATION_TITLE,
            notification_id=NOTIFICATION_ID,
        )
