"""State, start, estimated end and program sensors."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import PowerMonitorConfigEntry
from .detector import CycleState
from .entity import PowerMonitorEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PowerMonitorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    monitor = entry.runtime_data
    async_add_entities(
        [
            StateSensor(monitor, "state"),
            CycleStartSensor(monitor, "cycle_start"),
            EstimatedEndSensor(monitor, "estimated_end"),
            ProgramSensor(monitor, "detected_program"),
            RecordedCyclesSensor(monitor, "recorded_cycles"),
        ]
    )


class StateSensor(PowerMonitorEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [state.value for state in CycleState]

    @property
    def native_value(self) -> str:
        return self.monitor.detector.state.value


class CycleStartSensor(PowerMonitorEntity, SensorEntity):
    """Start of the running cycle, or of the last one when not running."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self) -> datetime | None:
        detector = self.monitor.detector
        if (cycle := detector.cycle or detector.last_cycle) is not None:
            return cycle.start
        if last := self.monitor.last_cycle:
            return dt_util.parse_datetime(last["start"])
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        detector = self.monitor.detector
        cycle = detector.cycle or detector.last_cycle
        # A cycle already running when monitoring began starts when noticed.
        return {"start_observed": cycle.observed_start if cycle else None}


class EstimatedEndSensor(PowerMonitorEntity, SensorEntity):
    """Estimated end of the running cycle, or when the last one ended."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self) -> datetime | None:
        if self.monitor.running:
            return self.monitor.estimated_end
        if (cycle := self.monitor.detector.last_cycle) is not None:
            return cycle.end
        if last := self.monitor.last_cycle:
            return dt_util.parse_datetime(last["end"])
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        monitor = self.monitor
        if not monitor.running or (cycle := monitor.detector.cycle) is None:
            return {"remaining_minutes": 0 if monitor.last_cycle else None}
        end = monitor.estimated_end
        if end is None:
            return {"remaining_minutes": None}
        now = dt_util.utcnow()
        elapsed = (now - cycle.start).total_seconds()
        total = (end - cycle.start).total_seconds()
        assert monitor.estimate is not None
        return {
            "remaining_minutes": round((end - now).total_seconds() / 60),
            "progress": round(100 * elapsed / total) if total > 0 else None,
            "matched_cycles": [m.template.id for m in monitor.estimate.matches],
        }


class ProgramSensor(PowerMonitorEntity, SensorEntity):
    """Program of the running cycle, or of the last one when not running."""

    @property
    def native_value(self) -> str | None:
        return self.monitor.current_program

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        monitor = self.monitor
        if monitor.running:
            estimate = monitor.estimate
            return {
                "source": "user" if monitor.selected_program else "detected",
                "confidence": estimate.confidence if estimate else None,
            }
        last = monitor.labelled_cycle
        return {
            "source": last["label_source"] if last else None,
            "confidence": None,
        }


class RecordedCyclesSensor(PowerMonitorEntity, SensorEntity):
    """Number of recorded cycles, listed with their ids for forget_cycle."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> int:
        return len(self.monitor.cycles)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        cycles = []
        for cycle in reversed(self.monitor.cycles):
            start = dt_util.parse_datetime(cycle["start"])
            end = dt_util.parse_datetime(cycle["end"])
            assert start is not None and end is not None
            cycles.append(
                {
                    "id": cycle["id"],
                    "program": cycle["program"],
                    "start": start.isoformat(),
                    "minutes": round((end - start).total_seconds() / 60),
                }
            )
        return {"cycles": cycles}
