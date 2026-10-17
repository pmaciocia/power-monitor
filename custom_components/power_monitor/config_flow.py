"""Config and options flow for Power Monitor."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME, UnitOfPower, UnitOfTime
from homeassistant.core import callback
from homeassistant.helpers import selector
import voluptuous as vol

from .const import (
    CONF_END_DELAY,
    CONF_END_POWER,
    CONF_FINISHED_TIMEOUT,
    CONF_POWER_ENTITY,
    CONF_PROGRAMS,
    CONF_STALE_TIMEOUT,
    CONF_START_DELAY,
    CONF_START_POWER,
    DEFAULT_OPTIONS,
    DOMAIN,
)


def _number(maximum: float, unit: str, step: float = 1) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0,
            max=maximum,
            step=step,
            unit_of_measurement=unit,
            mode=selector.NumberSelectorMode.BOX,
        )
    )


PROGRAMS_SELECTOR = selector.TextSelector(selector.TextSelectorConfig(multiple=True))

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_PROGRAMS): PROGRAMS_SELECTOR,
        vol.Required(CONF_START_POWER): _number(5000, UnitOfPower.WATT, 0.5),
        vol.Required(CONF_START_DELAY): _number(600, UnitOfTime.SECONDS),
        vol.Required(CONF_END_POWER): _number(5000, UnitOfPower.WATT, 0.5),
        vol.Required(CONF_END_DELAY): _number(120, UnitOfTime.MINUTES),
        vol.Required(CONF_STALE_TIMEOUT): _number(120, UnitOfTime.MINUTES),
        vol.Required(CONF_FINISHED_TIMEOUT): _number(1440, UnitOfTime.MINUTES),
    }
)


class PowerMonitorConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_POWER_ENTITY])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data={CONF_POWER_ENTITY: user_input[CONF_POWER_ENTITY]},
                options={
                    **DEFAULT_OPTIONS,
                    CONF_PROGRAMS: _clean(user_input.get(CONF_PROGRAMS, [])),
                },
            )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): selector.TextSelector(),
                    vol.Required(CONF_POWER_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain="sensor", device_class=SensorDeviceClass.POWER
                        )
                    ),
                    vol.Optional(CONF_PROGRAMS): PROGRAMS_SELECTOR,
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> PowerMonitorOptionsFlow:
        return PowerMonitorOptionsFlow()


class PowerMonitorOptionsFlow(OptionsFlow):
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            user_input[CONF_PROGRAMS] = _clean(user_input.get(CONF_PROGRAMS, []))
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, {**DEFAULT_OPTIONS, **self.config_entry.options}
            ),
        )


def _clean(programs: list[str]) -> list[str]:
    """Strip blanks and duplicates, keeping order."""
    return list(dict.fromkeys(p.strip() for p in programs if p.strip()))
