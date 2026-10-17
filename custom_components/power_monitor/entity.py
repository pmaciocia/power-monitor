"""Base entity for Power Monitor."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .monitor import CycleMonitor


class PowerMonitorEntity(Entity):
    """Entity updated whenever its monitor refreshes."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, monitor: CycleMonitor, key: str) -> None:
        self.monitor = monitor
        entry = monitor.entry
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.monitor.async_add_listener(self.async_write_ha_state))
