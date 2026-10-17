"""Running binary sensor."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import PowerMonitorConfigEntry
from .entity import PowerMonitorEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PowerMonitorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([RunningBinarySensor(entry.runtime_data, "running")])


class RunningBinarySensor(PowerMonitorEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    @property
    def is_on(self) -> bool:
        return self.monitor.running
