"""Cycle detection state machine.

Kept free of Home Assistant imports so it can be unit tested and replayed
against recorded history on its own.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum

# Sensors that report every N seconds jitter by a few milliseconds, so a
# 60 s delay would otherwise need three readings 30 s apart instead of two.
_JITTER = timedelta(seconds=2)


class CycleState(StrEnum):
    """Appliance state."""

    IDLE = "idle"
    RUNNING = "running"
    FINISHED = "finished"


@dataclass(frozen=True)
class DetectorConfig:
    """Thresholds for detecting the start and end of a cycle."""

    start_power: float
    start_delay: timedelta
    end_power: float
    end_delay: timedelta
    # No reading for this long is treated as 0 W from the last reading on.
    # Smoothing filters hold their last value when the source stops changing.
    stale_timeout: timedelta | None = None
    # FINISHED drops back to IDLE after this long, or stays until the next run.
    finished_timeout: timedelta | None = None


@dataclass
class Cycle:
    """A detected cycle and its raw readings."""

    start: datetime
    readings: list[tuple[datetime, float]] = field(default_factory=list)
    end: datetime | None = None


class CycleDetector:
    """Turn a stream of power readings into cycle start and end events."""

    def __init__(
        self,
        config: DetectorConfig,
        on_start: Callable[[Cycle], None] | None = None,
        on_end: Callable[[Cycle], None] | None = None,
    ) -> None:
        self.config = config
        self.state = CycleState.IDLE
        self.cycle: Cycle | None = None
        self.last_cycle: Cycle | None = None
        self._on_start = on_start
        self._on_end = on_end
        self._last_update: datetime | None = None
        self._last_power = 0.0
        self._above_since: datetime | None = None
        self._pending: list[tuple[datetime, float]] = []
        self._below_since: datetime | None = None
        self._finished_at: datetime | None = None

    def update(self, ts: datetime, power: float) -> None:
        """Process a new reading from the power sensor."""
        self._last_update = ts
        self._last_power = power
        self._process(ts, power, record=True)

    def tick(self, now: datetime) -> None:
        """Re-evaluate timers when no new reading has arrived."""
        if self.state is CycleState.FINISHED and self.config.finished_timeout:
            assert self._finished_at is not None
            if now - self._finished_at >= self.config.finished_timeout:
                self.state = CycleState.IDLE
        if self._last_update is None:
            return
        stale = self.config.stale_timeout
        if stale and now - self._last_update >= stale and self._last_power:
            # Assume the source went quiet because the power dropped to zero.
            since = self._last_update
            self._last_power = 0.0
            if self.state is CycleState.RUNNING and self._below_since is None:
                self._below_since = since
            self._process(now, 0.0, record=False)
            return
        self._process(now, self._last_power, record=False)

    def resume(self, cycle: Cycle, now: datetime) -> None:
        """Continue a cycle that was in progress before a restart."""
        self.cycle = cycle
        self.state = CycleState.RUNNING
        if cycle.readings:
            self._last_update, self._last_power = cycle.readings[-1]
        self.tick(now)

    def _process(self, ts: datetime, power: float, *, record: bool) -> None:
        if self.state is CycleState.RUNNING:
            self._process_running(ts, power, record=record)
        else:
            self._process_waiting(ts, power, record=record)

    def _process_waiting(self, ts: datetime, power: float, *, record: bool) -> None:
        if power < self.config.start_power:
            self._above_since = None
            self._pending.clear()
            return
        if self._above_since is None:
            self._above_since = ts
        if record:
            self._pending.append((ts, power))
        if ts - self._above_since < self.config.start_delay - _JITTER:
            return
        self.cycle = Cycle(start=self._above_since, readings=list(self._pending))
        self.state = CycleState.RUNNING
        self._above_since = None
        self._below_since = None
        self._pending.clear()
        if self._on_start:
            self._on_start(self.cycle)

    def _process_running(self, ts: datetime, power: float, *, record: bool) -> None:
        assert self.cycle is not None
        if record:
            self.cycle.readings.append((ts, power))
        if power >= self.config.end_power:
            self._below_since = None
            return
        if self._below_since is None:
            self._below_since = ts
        if ts - self._below_since < self.config.end_delay - _JITTER:
            return
        cycle = self.cycle
        cycle.end = self._below_since
        cycle.readings = [r for r in cycle.readings if r[0] <= cycle.end]
        self.last_cycle = cycle
        self.cycle = None
        self.state = CycleState.FINISHED
        self._finished_at = ts
        self._below_since = None
        if self._on_end:
            self._on_end(cycle)
