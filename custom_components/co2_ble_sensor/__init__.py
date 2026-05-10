"""CO2 BLE Sensor integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    CONF_CONNECTION_MODE,
    CONF_SCAN_INTERVAL,
    DEFAULT_CONNECTION_MODE,
    DEFAULT_SCAN_INTERVAL,
)
from .coordinator import CO2BLECoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up CO2 BLE Sensor from config entry."""
    hass.data.setdefault(DOMAIN, {})

    coordinator = CO2BLECoordinator(
        hass=hass,
        address=entry.data["address"],
        local_key=entry.data["local_key"],
        uuid=entry.data["uuid"],
        device_id=entry.data["device_id"],
        name=entry.title,
        connection_mode=entry.options.get(CONF_CONNECTION_MODE, DEFAULT_CONNECTION_MODE),
        scan_interval=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await coordinator.async_start()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload config entry."""
    coordinator: CO2BLECoordinator = hass.data[DOMAIN].get(entry.entry_id)
    if coordinator:
        await coordinator.async_stop()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload entry when options change."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
