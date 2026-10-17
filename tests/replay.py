"""Replay recorded readings through the detector like Home Assistant would."""

from __future__ import annotations

from datetime import datetime, timedelta

from custom_components.power_monitor.detector import (
    Cycle,
    CycleDetector,
    DetectorConfig,
)

TICK = timedelta(seconds=30)

WASHER = DetectorConfig(
    start_power=15,
    start_delay=timedelta(seconds=60),
    end_power=5,
    end_delay=timedelta(minutes=5),
    stale_timeout=timedelta(minutes=5),
)


def replay(
    readings: list[tuple[datetime, float]],
    config: DetectorConfig = WASHER,
    until: datetime | None = None,
) -> tuple[list[Cycle], CycleDetector]:
    """Feed readings with a tick every 30 s in between, as the monitor does."""
    finished: list[Cycle] = []
    detector = CycleDetector(config, on_end=finished.append)
    for i, (ts, power) in enumerate(readings):
        detector.update(ts, power)
        stop = readings[i + 1][0] if i + 1 < len(readings) else until or ts
        tick = ts + TICK
        while tick < stop:
            detector.tick(tick)
            tick += TICK
    return finished, detector
