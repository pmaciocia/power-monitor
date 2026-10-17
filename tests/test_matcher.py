"""Matcher tests against synthetic washing machine cycles."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from custom_components.power_monitor.matcher import CycleMatcher, Template, resample

from replay import replay

STEP = timedelta(seconds=30)


@pytest.fixture
def cycles(raw_readings):
    finished, _ = replay(raw_readings)
    return [resample(c.readings, c.start, c.end, STEP) for c in finished]


def test_resample_time_weighted():
    start = datetime.fromisoformat("2026-01-01T00:00:00+00:00")
    readings = [
        (start, 100.0),
        (start + timedelta(seconds=15), 0.0),
        (start + timedelta(seconds=60), 50.0),
    ]

    assert resample(readings, start, start + timedelta(seconds=90), STEP) == [
        50.0,
        0.0,
        50.0,
    ]


@pytest.mark.parametrize(("template", "run"), [(0, 1), (1, 0)])
def test_remaining_time_against_other_wash(cycles, template, run):
    matcher = CycleMatcher([Template("t", None, cycles[template])], STEP)
    live = cycles[run]
    errors = []
    for n in range(1, len(live) + 1):
        matcher.extend(live[:n])
        remaining = matcher.estimate().remaining.total_seconds()
        errors.append(abs(remaining - (len(live) - n) * STEP.total_seconds()) / 60)

    # Assuming the same pace as the other wash is out by the difference in
    # their lengths throughout. Alignment should do clearly better on average.
    same_pace = abs(len(cycles[template]) - len(live)) * STEP.total_seconds() / 60
    assert sum(errors) / len(errors) < same_pace * 0.75
    assert max(errors) < 15


def test_detects_program(cycles):
    templates = [
        Template("a", "Cottons", cycles[0]),
        Template("b", "Synthetics", cycles[1]),
    ]
    for expected, live in (("Cottons", cycles[0]), ("Synthetics", cycles[1])):
        matcher = CycleMatcher(templates, STEP)
        # 45 min in: past heating, into the wash phase where they differ.
        matcher.extend(live[:90])
        estimate = matcher.estimate()
        assert estimate.program == expected
        assert estimate.confidence > 0.3


def test_selected_program_restricts_templates(cycles):
    templates = [
        Template("a", "Cottons", cycles[0]),
        Template("b", "Synthetics", cycles[1]),
    ]
    matcher = CycleMatcher(templates, STEP)
    matcher.extend(cycles[0][:90])

    estimate = matcher.estimate(program="Synthetics")

    assert estimate.program == "Synthetics"
    assert [m.template.id for m in estimate.matches] == ["b"]


def test_no_templates_gives_no_estimate():
    matcher = CycleMatcher([], STEP)
    matcher.extend([2000.0] * 10)

    assert matcher.estimate().remaining is None
