"""Tie the detector and matcher to a power sensor and persist cycles."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
import logging
from typing import Any
import uuid

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    EventStateReportedData,
    HomeAssistant,
    callback,
)
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_state_report_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    AUTO_LABEL_CONFIDENCE,
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
    MAX_CYCLES_PER_PROGRAM,
    MAX_UNLABELLED_CYCLES,
    MIN_CYCLE_DURATION,
    STEP,
    STORAGE_VERSION,
)
from .detector import Cycle, CycleDetector, CycleState, DetectorConfig
from .matcher import CycleMatcher, Estimate, Template, resample

_LOGGER = logging.getLogger(__name__)

SAVE_DELAY = 60  # s, while a cycle is running


def _minutes(value: float) -> timedelta | None:
    return timedelta(minutes=value) if value else None


def detector_config(options: dict[str, Any]) -> DetectorConfig:
    return DetectorConfig(
        start_power=options[CONF_START_POWER],
        start_delay=timedelta(seconds=options[CONF_START_DELAY]),
        end_power=options[CONF_END_POWER],
        end_delay=timedelta(minutes=options[CONF_END_DELAY]),
        stale_timeout=_minutes(options[CONF_STALE_TIMEOUT]),
        finished_timeout=_minutes(options[CONF_FINISHED_TIMEOUT]),
    )


class CycleMonitor:
    """Follow one appliance's power sensor and estimate its cycles."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        options = {**DEFAULT_OPTIONS, **entry.options}
        self.power_entity: str = entry.data[CONF_POWER_ENTITY]
        self.configured_programs: list[str] = options[CONF_PROGRAMS]
        self.detector = CycleDetector(
            detector_config(options), on_start=self._on_start, on_end=self._on_end
        )
        # Recorded cycles, oldest first, as stored.
        self.cycles: list[dict[str, Any]] = []
        self.estimate: Estimate | None = None
        self.estimated_end: datetime | None = None
        # Program picked by the user for the running cycle.
        self.selected_program: str | None = None
        self._matcher: CycleMatcher | None = None
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self._listeners: list[CALLBACK_TYPE] = []
        self._unsubs: list[CALLBACK_TYPE] = []

    # Lifecycle

    async def async_start(self) -> None:
        data = await self._store.async_load() or {}
        self.cycles = data.get("cycles", [])
        if current := data.get("current"):
            self._resume(current)
        # A repeated identical value (e.g. a steady heater) is only a state
        # report, not a change, but it still shows the sensor is alive.
        self._unsubs.append(
            async_track_state_change_event(
                self.hass, self.power_entity, self._handle_state_event
            )
        )
        self._unsubs.append(
            async_track_state_report_event(
                self.hass, self.power_entity, self._handle_state_event
            )
        )
        self._unsubs.append(
            async_track_time_interval(self.hass, self._handle_tick, STEP)
        )
        if state := self.hass.states.get(self.power_entity):
            if (power := _power(state.state)) is not None:
                self.detector.update(state.last_reported, power)
        self._refresh()

    async def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        await self._store.async_save(self._data_to_save())

    def _resume(self, current: dict[str, Any]) -> None:
        start = dt_util.parse_datetime(current["start"])
        assert start is not None
        readings = [(start + timedelta(seconds=s), p) for s, p in current["readings"]]
        self.selected_program = current.get("program")
        _LOGGER.debug("Resuming %s cycle started %s", self.power_entity, start)
        cycle = Cycle(
            start=start,
            readings=readings,
            observed_start=current.get("observed_start", True),
        )
        self.detector.resume(cycle, dt_util.utcnow())

    # Listeners for entities

    @callback
    def async_add_listener(self, update: CALLBACK_TYPE) -> Callable[[], None]:
        self._listeners.append(update)
        return lambda: self._listeners.remove(update)

    @callback
    def _notify(self) -> None:
        for update in list(self._listeners):
            update()

    # Inputs

    @callback
    def _handle_state_event(
        self, event: Event[EventStateChangedData] | Event[EventStateReportedData]
    ) -> None:
        state = event.data["new_state"]
        if state is None or (power := _power(state.state)) is None:
            return
        self.detector.update(state.last_reported, power)
        self._refresh()

    @callback
    def _handle_tick(self, now: datetime) -> None:
        self.detector.tick(now)
        self._refresh()

    # Detector callbacks

    def _on_start(self, cycle: Cycle) -> None:
        _LOGGER.debug("%s cycle started at %s", self.power_entity, cycle.start)
        self.selected_program = None
        self._matcher = None

    def _on_end(self, cycle: Cycle) -> None:
        assert cycle.end is not None
        if not cycle.observed_start:
            _LOGGER.debug("%s cycle joined part way, not recorded", self.power_entity)
        elif cycle.end - cycle.start < MIN_CYCLE_DURATION:
            _LOGGER.debug("%s cycle too short, not recorded", self.power_entity)
        else:
            self._record(cycle)
        self.selected_program = None
        self._matcher = None
        self.estimate = None
        self.estimated_end = None
        self._store.async_delay_save(self._data_to_save, 0)

    def _record(self, cycle: Cycle) -> None:
        assert cycle.end is not None
        program, source = self.selected_program, "user"
        if program is None and self.estimate and self.estimate.program:
            confidence = self.estimate.confidence
            if confidence is not None and confidence >= AUTO_LABEL_CONFIDENCE:
                program, source = self.estimate.program, "auto"
        samples = resample(cycle.readings, cycle.start, cycle.end, STEP)
        _LOGGER.debug(
            "%s cycle %s - %s finished, program %s",
            self.power_entity,
            cycle.start,
            cycle.end,
            program,
        )
        self.cycles.append(
            {
                "id": uuid.uuid4().hex,
                "start": cycle.start.isoformat(),
                "end": cycle.end.isoformat(),
                "step": STEP.total_seconds(),
                "program": program,
                "label_source": source if program else None,
                "energy_kwh": round(sum(samples) * STEP.total_seconds() / 3.6e6, 3),
                "samples": [round(p, 1) for p in samples],
            }
        )
        self._prune()

    # Estimation

    @callback
    def _refresh(self) -> None:
        cycle = self.detector.cycle
        if self.detector.state is CycleState.RUNNING and cycle is not None:
            self._store.async_delay_save(self._data_to_save, SAVE_DELAY)
        # Matching aligns from the start, so a cycle joined part way can't be
        # placed against recorded ones.
        if self.running and cycle is not None and cycle.observed_start:
            now = dt_util.utcnow()
            if self._matcher is None:
                self._matcher = CycleMatcher(self._templates(), STEP)
            self._matcher.extend(resample(cycle.readings, cycle.start, now, STEP))
            self.estimate = self._matcher.estimate(self.selected_program)
            remaining = self.estimate.remaining
            self.estimated_end = (
                max(now, cycle.start + STEP * self._matcher.samples + remaining)
                if remaining is not None
                else None
            )
        self._notify()

    def _templates(self) -> list[Template]:
        return [
            Template(c["id"], c["program"], c["samples"])
            for c in self.cycles
            if c["step"] == STEP.total_seconds()
        ]

    def _prune(self) -> None:
        kept: list[dict[str, Any]] = []
        counts: dict[str | None, int] = {}
        for cycle in reversed(self.cycles):
            program = cycle["program"]
            limit = MAX_CYCLES_PER_PROGRAM if program else MAX_UNLABELLED_CYCLES
            if counts.get(program, 0) < limit:
                counts[program] = counts.get(program, 0) + 1
                kept.append(cycle)
        self.cycles = kept[::-1]

    # Programs

    @property
    def programs(self) -> list[str]:
        """Configured programs plus any found only in recorded cycles."""
        programs = list(self.configured_programs)
        for cycle in self.cycles:
            if cycle["program"] and cycle["program"] not in programs:
                programs.append(cycle["program"])
        return programs

    @property
    def last_cycle(self) -> dict[str, Any] | None:
        return self.cycles[-1] if self.cycles else None

    @property
    def running(self) -> bool:
        return self.detector.state is CycleState.RUNNING

    @property
    def current_program(self) -> str | None:
        """Program of the running cycle, or of the last one when not running."""
        if self.running:
            if self.selected_program:
                return self.selected_program
            return self.estimate.program if self.estimate else None
        return self.last_cycle["program"] if self.last_cycle else None

    @callback
    def async_set_program(self, program: str | None) -> None:
        """Set the running cycle's program, or relabel the last cycle."""
        if self.running:
            self.selected_program = program
            self._refresh()
            return
        if (last := self.last_cycle) is None:
            return
        last["program"] = program
        last["label_source"] = "user" if program else None
        self._prune()
        self._store.async_delay_save(self._data_to_save, 0)
        self._notify()

    # Storage

    def _data_to_save(self) -> dict[str, Any]:
        data: dict[str, Any] = {"cycles": self.cycles}
        if (cycle := self.detector.cycle) is not None:
            data["current"] = {
                "start": cycle.start.isoformat(),
                "program": self.selected_program,
                "observed_start": cycle.observed_start,
                "readings": [
                    [round((ts - cycle.start).total_seconds(), 1), p]
                    for ts, p in cycle.readings
                ],
            }
        return data


def _power(state: str) -> float | None:
    if state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return None
    try:
        return float(state)
    except ValueError:
        return None
