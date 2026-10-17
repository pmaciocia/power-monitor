"""Detector tests against synthetic washing machine history."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from custom_components.power_monitor.detector import CycleState

from replay import WASHER, replay

START = datetime.fromisoformat("2026-01-01T10:00:00+00:00")


def readings_every_30s(powers: list[float]) -> list[tuple[datetime, float]]:
    return [(START + timedelta(seconds=30 * i), p) for i, p in enumerate(powers)]


def minutes(ts: datetime) -> str:
    return ts.isoformat(timespec="minutes")


def test_raw_sensor_cycles(raw_readings):
    cycles, detector = replay(raw_readings)

    # Starts at the agitation after a minute of the display drawing 8.8 W.
    assert [(minutes(c.start), minutes(c.end)) for c in cycles] == [
        ("2026-01-12T09:01+00:00", "2026-01-12T11:11+00:00"),
        ("2026-01-13T14:01+00:00", "2026-01-13T16:07+00:00"),
    ]
    # The fixture ends mid-cycle.
    assert detector.state is CycleState.RUNNING
    assert minutes(detector.cycle.start) == "2026-01-15T19:00+00:00"


def test_filtered_sensor_ends_via_stale_timeout(filtered_readings):
    """The filter sensor holds ~12 W after the machine switches off."""
    cycles, _ = replay(filtered_readings)

    assert [minutes(c.end) for c in cycles] == [
        "2026-01-12T11:12+00:00",
        "2026-01-13T16:07+00:00",
    ]


def test_filtered_sensor_never_ends_without_stale_timeout(filtered_readings):
    cycles, _ = replay(filtered_readings, replace(WASHER, stale_timeout=None))

    # Only ends once the plug reports standby power, a day later.
    assert cycles[0].end.date().isoformat() == "2026-01-13"


def test_short_pause_does_not_end_cycle():
    readings = readings_every_30s([2000] * 10 + [2.5] * 8 + [150] * 10 + [0] * 20)

    cycles, _ = replay(readings)

    assert len(cycles) == 1
    assert cycles[0].end == START + timedelta(seconds=30 * 28)


def test_display_on_is_not_a_start():
    _, detector = replay(readings_every_30s([8.8] * 20))

    assert detector.state is CycleState.IDLE


def test_finished_timeout_returns_to_idle():
    readings = readings_every_30s([2000] * 10 + [0])
    config = replace(WASHER, finished_timeout=timedelta(minutes=30))

    _, detector = replay(readings, config, until=START + timedelta(minutes=20))
    assert detector.state is CycleState.FINISHED

    _, detector = replay(readings, config, until=START + timedelta(minutes=60))
    assert detector.state is CycleState.IDLE


# The wash phase: drum on for a minute, then a 30 s pause at ~2.4 W.
WASH_PHASE = [150, 155, 2.4] * 10


def test_drum_pauses_do_not_prevent_start():
    _, detector = replay(readings_every_30s([1.5] * 12 + WASH_PHASE))

    assert detector.state is CycleState.RUNNING
    assert detector.cycle.start == START + timedelta(minutes=6)
    assert detector.cycle.observed_start


def test_joined_part_way_is_not_observed_start():
    """Set up while the machine is already mid-wash."""
    _, detector = replay(readings_every_30s(WASH_PHASE))

    assert detector.state is CycleState.RUNNING
    assert not detector.cycle.observed_start


def test_short_quiet_before_start_is_not_observed_start():
    """A rinse pause shorter than the end delay doesn't count as idle."""
    _, detector = replay(readings_every_30s([2.4] * 6 + WASH_PHASE))

    assert not detector.cycle.observed_start


def test_spike_is_not_a_start():
    _, detector = replay(readings_every_30s([1.5] * 12 + [120] + [1.5] * 10))

    assert detector.state is CycleState.IDLE


def test_cycle_after_finished_is_observed_start():
    readings = readings_every_30s([1.5] * 12 + [2000] * 10 + [0] * 12 + WASH_PHASE)

    cycles, detector = replay(readings)

    assert cycles[0].observed_start
    assert detector.cycle.observed_start
