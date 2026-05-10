"""Sensor platform for CO2 BLE Sensor."""
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_MILLION,
    PERCENTAGE,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_UPDATE
from .coordinator import CO2BLECoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass
class CO2SensorEntityDescription(SensorEntityDescription):
    """Description for CO2 BLE sensor."""
    data_key: str = ""
    scale: float = 1.0


SENSOR_DESCRIPTIONS = [
    CO2SensorEntityDescription(
        key="co2",
        data_key="co2",
        name="CO2",
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
        device_class=SensorDeviceClass.CO2,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:molecule-co2",
    ),
    CO2SensorEntityDescription(
        key="temperature",
        data_key="temperature",
        name="Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    CO2SensorEntityDescription(
        key="humidity",
        data_key="humidity",
        name="Humidity",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    CO2SensorEntityDescription(
        key="battery",
        data_key="battery",
        name="Battery",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    CO2SensorEntityDescription(
        key="co2_state",
        data_key="co2_state",
        name="CO2 State",
        icon="mdi:air-filter",
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities."""
    coordinator: CO2BLECoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        CO2BLESensorEntity(coordinator, description)
        for description in SENSOR_DESCRIPTIONS
    ]
    async_add_entities(entities)


class CO2BLESensorEntity(SensorEntity):
    """CO2 BLE Sensor entity."""

    entity_description: CO2SensorEntityDescription

    def __init__(
        self,
        coordinator: CO2BLECoordinator,
        description: CO2SensorEntityDescription,
    ) -> None:
        self.entity_description = description
        self._coordinator = coordinator
        self._attr_unique_id = f"{coordinator.address}_{description.key}"
        self._attr_has_entity_name = True
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            name=coordinator.name,
            manufacturer="Tuya / MOES",
            model="BSS-X-CO2-U",
        )

    @property
    def native_value(self) -> Any:
        return self._coordinator.data.get(self.entity_description.data_key)

    @property
    def available(self) -> bool:
        return self.entity_description.data_key in self._coordinator.data

    async def async_added_to_hass(self) -> None:
        """Subscribe to updates."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_UPDATE}_{self._coordinator.address}",
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
        """Handle data update."""
        self.async_write_ha_state()
