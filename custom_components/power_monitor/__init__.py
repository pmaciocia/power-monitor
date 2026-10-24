"""Power Monitor: detect appliance cycles from a power sensor and estimate when they end."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
import voluptuous as vol

from .const import ATTR_CONFIG_ENTRY_ID, ATTR_CYCLE_ID, DOMAIN, SERVICE_FORGET_CYCLE
from .monitor import CycleMonitor

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SELECT, Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

FORGET_CYCLE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_CYCLE_ID): cv.string,
    }
)

type PowerMonitorConfigEntry = ConfigEntry[CycleMonitor]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async def forget_cycle(call: ServiceCall) -> None:
        entry_id = call.data[ATTR_CONFIG_ENTRY_ID]
        entry = hass.config_entries.async_get_entry(entry_id)
        if (
            entry is None
            or entry.domain != DOMAIN
            or entry.state is not ConfigEntryState.LOADED
        ):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="entry_not_loaded",
                translation_placeholders={"entry_id": entry_id},
            )
        cycle_id = call.data[ATTR_CYCLE_ID]
        if not entry.runtime_data.async_forget_cycle(cycle_id):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="cycle_not_found",
                translation_placeholders={"cycle_id": cycle_id},
            )

    hass.services.async_register(
        DOMAIN, SERVICE_FORGET_CYCLE, forget_cycle, schema=FORGET_CYCLE_SCHEMA
    )
    return True


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
