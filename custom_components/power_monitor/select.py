"""Program select: override the running cycle's program or label the last one."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import PowerMonitorConfigEntry
from .const import UNKNOWN_PROGRAM
from .entity import PowerMonitorEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PowerMonitorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([ProgramSelect(entry.runtime_data, "program")])


class ProgramSelect(PowerMonitorEntity, SelectEntity):
    @property
    def options(self) -> list[str]:
        return [UNKNOWN_PROGRAM, *self.monitor.programs]

    @property
    def current_option(self) -> str:
        return self.monitor.current_program or UNKNOWN_PROGRAM

    async def async_select_option(self, option: str) -> None:
        self.monitor.async_set_program(None if option == UNKNOWN_PROGRAM else option)
