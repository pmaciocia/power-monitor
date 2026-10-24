"""End-to-end tests of the integration in Home Assistant."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util
import pytest
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


ENTRY_ID = "washer"


async def setup(hass: HomeAssistant) -> MockConfigEntry:
    hass.states.async_set(POWER, "1.5", {"unit_of_measurement": "W"})
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Washing machine",
        entry_id=ENTRY_ID,
        unique_id=POWER,
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


async def record_wash(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, program: str
) -> None:
    await run(hass, freezer, IDLE + WASH)
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.washing_machine_program", "option": program},
        blocking=True,
    )


async def test_forget_cycle(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup(hass)
    await record_wash(hass, freezer, "Cottons")
    await record_wash(hass, freezer, "Eco")

    recorded = hass.states.get("sensor.washing_machine_recorded_cycles")
    assert recorded.state == "2"
    newest, oldest = recorded.attributes["cycles"]
    assert (newest["program"], oldest["program"]) == ("Eco", "Cottons")
    assert newest["minutes"] == 35

    await hass.services.async_call(
        DOMAIN,
        "forget_cycle",
        {"config_entry_id": entry.entry_id, "cycle_id": oldest["id"]},
        blocking=True,
    )

    assert [c["program"] for c in entry.runtime_data.cycles] == ["Eco"]
    assert hass.states.get("sensor.washing_machine_recorded_cycles").state == "1"


async def test_forget_unknown_cycle_raises(hass: HomeAssistant) -> None:
    entry = await setup(hass)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "forget_cycle",
            {"config_entry_id": entry.entry_id, "cycle_id": "nope"},
            blocking=True,
        )


async def test_label_after_unrecorded_cycle_keeps_previous_label(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup(hass)
    await record_wash(hass, freezer, "Cottons")

    # A 5 minute run, too short to record.
    await run(hass, freezer, [2000.0] * 10 + [0.0] * 12)
    assert hass.states.get("select.washing_machine_program").state == "Unknown"
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.washing_machine_program", "option": "Eco"},
        blocking=True,
    )

    assert [c["program"] for c in entry.runtime_data.cycles] == ["Cottons"]


async def test_resumed_cycle_without_flag_is_not_recorded(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, hass_storage
) -> None:
    """A cycle saved by 0.1.0 may have been joined part way."""
    start = dt_util.utcnow() - timedelta(minutes=10)
    hass_storage[f"{DOMAIN}.{ENTRY_ID}"] = {
        "version": 1,
        "minor_version": 1,
        "key": f"{DOMAIN}.{ENTRY_ID}",
        "data": {
            "cycles": [],
            "current": {
                "start": start.isoformat(),
                "program": None,
                "readings": [[30 * i, 150.0] for i in range(20)],
            },
        },
    }
    entry = await setup(hass)
    assert hass.states.get("sensor.washing_machine_state").state == "running"

    await run(hass, freezer, [150.0] * 20 + [0.0] * 12)

    assert hass.states.get("sensor.washing_machine_state").state == "finished"
    assert entry.runtime_data.cycles == []


async def test_reconfigure_changes_sensor_and_keeps_cycles(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup(hass)
    await record_wash(hass, freezer, "Cottons")
    hass.states.async_set(
        "sensor.washer_power_raw", "0.0", {"unit_of_measurement": "W"}
    )

    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_POWER_ENTITY: "sensor.washer_power_raw"}
    )
    await hass.async_block_till_done()

    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_POWER_ENTITY] == "sensor.washer_power_raw"
    assert entry.unique_id == "sensor.washer_power_raw"
    assert entry.runtime_data.power_entity == "sensor.washer_power_raw"
    assert [c["program"] for c in entry.runtime_data.cycles] == ["Cottons"]


async def test_reconfigure_rejects_sensor_monitored_by_other_entry(
    hass: HomeAssistant,
) -> None:
    entry = await setup(hass)
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="sensor.dryer_power",
        data={CONF_POWER_ENTITY: "sensor.dryer_power"},
    ).add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_POWER_ENTITY: "sensor.dryer_power"}
    )

    assert result["reason"] == "already_configured"
    assert entry.data[CONF_POWER_ENTITY] == POWER
