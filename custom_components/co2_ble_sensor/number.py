"""Number platform for CO2 BLE Sensor — CO2 alarm threshold."""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONCENTRATION_PARTS_PER_MILLION
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_UPDATE
from .coordinator import CO2BLECoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: CO2BLECoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([CO2AlarmThresholdNumber(coordinator)])


class CO2AlarmThresholdNumber(NumberEntity):
    """Number entity for CO2 alarm threshold (DP26)."""

    _attr_name = "CO2 Alarm Threshold"
    _attr_icon = "mdi:molecule-co2"
    _attr_native_unit_of_measurement = CONCENTRATION_PARTS_PER_MILLION
    _attr_native_min_value = 400
    _attr_native_max_value = 5000
    _attr_native_step = 100
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: CO2BLECoordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{coordinator.address}_co2_alarm_threshold"
        self._attr_has_entity_name = True
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            name=coordinator.name,
            manufacturer="Tuya / MOES",
            model="BSS-X-CO2-U",
        )

    @property
    def native_value(self) -> float | None:
        return self._coordinator.data.get("co2_alarm_threshold")

    @property
    def available(self) -> bool:
        return "co2_alarm_threshold" in self._coordinator.data

    async def async_set_native_value(self, value: float) -> None:
        """Send new threshold to device."""
        if self._coordinator._client:
            ok = await self._coordinator._client.set_co2_alarm_threshold(int(value))
            if ok:
                self._coordinator.data["co2_alarm_threshold"] = int(value)
                self.async_write_ha_state()
            else:
                _LOGGER.error("Failed to set CO2 alarm threshold")

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_UPDATE}_{self._coordinator.address}",
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()
