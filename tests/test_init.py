"""End-to-end tests of the integration in Home Assistant."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.power_monitor.const import (
    CONF_POWER_ENTITY,
    CONF_PROGRAMS,
    DEFAULT_OPTIONS,
    DOMAIN,
)

POWER = "sensor.washer_power"


async def setup(hass: HomeAssistant) -> MockConfigEntry:
    hass.states.async_set(POWER, "1.5", {"unit_of_measurement": "W"})
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Washing machine",
        data={CONF_POWER_ENTITY: POWER},
        options={**DEFAULT_OPTIONS, CONF_PROGRAMS: ["Cottons", "Eco"]},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def run(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, powers: list[float]
) -> None:
    """Report each power for 30 s, like a plug polled every 30 s."""
    for power in powers:
        hass.states.async_set(POWER, str(power), {"unit_of_measurement": "W"})
        freezer.tick(timedelta(seconds=30))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()


WASH = [2000.0] * 20 + [150.0] * 40 + [400.0] * 10 + [0.0] * 12
# Standby long enough for the next start to count as seen from the start.
IDLE = [1.5] * 12


async def test_entities_created(hass: HomeAssistant) -> None:
    await setup(hass)

    assert hass.states.get("sensor.washing_machine_state").state == "idle"
    assert hass.states.get("binary_sensor.washing_machine_running").state == "off"
    assert hass.states.get("sensor.washing_machine_estimated_end").state == "unknown"
    select = hass.states.get("select.washing_machine_program")
    assert select.state == "Unknown"
    assert select.attributes["options"] == ["Unknown", "Cottons", "Eco"]


async def test_cycle_recorded_labelled_and_matched(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup(hass)

    # First wash: no history, so no estimate.
    await run(hass, freezer, IDLE + WASH[:30])
    assert hass.states.get("sensor.washing_machine_state").state == "running"
    assert hass.states.get("binary_sensor.washing_machine_running").state == "on"
    assert hass.states.get("sensor.washing_machine_estimated_end").state == "unknown"

    await run(hass, freezer, WASH[30:])
    assert hass.states.get("sensor.washing_machine_state").state == "finished"
    assert len(entry.runtime_data.cycles) == 1

    # Label it after the fact.
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.washing_machine_program", "option": "Cottons"},
        blocking=True,
    )
    assert entry.runtime_data.cycles[0]["program"] == "Cottons"
    assert entry.runtime_data.cycles[0]["label_source"] == "user"

    # Second wash: matched against the first, 10 minutes in.
    await run(hass, freezer, WASH[:20])
    assert hass.states.get("sensor.washing_machine_detected_program").state == "Cottons"
    end = hass.states.get("sensor.washing_machine_estimated_end")
    assert end.state != "unknown"
    # 70 samples long minus 20 done is 25 min, give or take a sample.
    assert 24 <= end.attributes["remaining_minutes"] <= 26


async def test_running_cycle_survives_reload(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup(hass)
    await run(hass, freezer, IDLE + WASH[:30])
    start = hass.states.get("sensor.washing_machine_cycle_start").state

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.washing_machine_state").state == "running"
    cycle_start = hass.states.get("sensor.washing_machine_cycle_start")
    assert cycle_start.state == start
    assert cycle_start.attributes["start_observed"] is True
    assert len(entry.runtime_data.detector.cycle.readings) >= 30


async def test_cycle_joined_part_way_is_not_recorded(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Set up while the machine is already mid-wash, with drum pauses."""
    entry = await setup(hass)
    await run(hass, freezer, [150.0, 155.0, 2.4] * 10)

    assert hass.states.get("sensor.washing_machine_state").state == "running"
    cycle_start = hass.states.get("sensor.washing_machine_cycle_start")
    assert cycle_start.attributes["start_observed"] is False
    assert hass.states.get("sensor.washing_machine_estimated_end").state == "unknown"

    await run(hass, freezer, [400.0] * 10 + [0.0] * 12)
    assert hass.states.get("sensor.washing_machine_state").state == "finished"
    assert entry.runtime_data.cycles == []
    assert hass.states.get("sensor.washing_machine_estimated_end").state != "unknown"
