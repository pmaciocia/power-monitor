"""Power Monitor: detect appliance cycles from a power sensor and estimate when they end."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .monitor import CycleMonitor

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SELECT, Platform.SENSOR]

type PowerMonitorConfigEntry = ConfigEntry[CycleMonitor]


async def async_setup_entry(
    hass: HomeAssistant, entry: PowerMonitorConfigEntry
) -> bool:
    monitor = CycleMonitor(hass, entry)
    await monitor.async_start()
    entry.runtime_data = monitor
    entry.async_on_unload(monitor.async_stop)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: PowerMonitorConfigEntry
) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(
    hass: HomeAssistant, entry: PowerMonitorConfigEntry
) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
