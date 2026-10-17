"""Generate synthetic washing machine power history for the tests.

The traces mimic a real machine on a smart plug reporting every 30 s:

- ~1.5 W standby, ~8.8 W with the display on before a program starts
- a short agitation, then ~17 min heating at 2.2-2.4 kW
- a wash phase at a load-dependent level with brief ~2.5 W drum pauses
- a rinse phase alternating between pauses and short drum movements
- a 330-440 W spin, a short drain, then 0 W once the machine switches off

Like the recorder, only changed values are written, so the plug goes quiet at
0 W after a cycle. The filtered file mimics a moving-average `filter` sensor,
which only recalculates when the source changes and so holds a non-zero value
after the machine switches off.

Run from the repo root: `uv run python tests/fixtures/generate.py`
"""

from __future__ import annotations

from collections import deque
import csv
from datetime import datetime, timedelta
from pathlib import Path
import random

HERE = Path(__file__).parent
STEP = timedelta(seconds=30)


def _cycle(
    rng: random.Random, wash_level: float, heat: int, wash: int, rinse: int
) -> list[float]:
    """Power every 30 s for one cycle. Durations are in minutes."""
    powers = [rng.uniform(40, 110) for _ in range(8)]  # fill and agitate
    powers += [rng.uniform(2200, 2390) for _ in range(heat * 2)]
    powers.append(rng.uniform(1100, 1200))  # heater switching off
    for i in range(wash * 2):
        pause = i % 6 == 5
        powers.append(
            rng.uniform(2.4, 2.6) if pause else wash_level + rng.uniform(-8, 8)
        )
    for _ in range(rinse * 2):
        powers.append(
            rng.choice(
                [rng.uniform(2.4, 2.6), 8.8, rng.uniform(20, 21), rng.uniform(50, 150)]
                + [rng.uniform(230, 360)] * (rng.random() < 0.1)
            )
        )
    powers += [rng.uniform(330, 440) for _ in range(8)]  # spin
    powers += [rng.uniform(23.7, 24.0) for _ in range(3)]  # drain
    powers += [rng.uniform(1.9, 2.1), 0.0]
    return powers


def _standby(rng: random.Random, minutes: int) -> list[float]:
    return [round(rng.uniform(1.4, 1.55), 2) for _ in range(minutes * 2)]


def _display(minutes: int) -> list[float]:
    return [8.8] * (minutes * 2)


def _readings(rng: random.Random) -> list[tuple[datetime, float]]:
    # (start time, powers every 30 s from then on)
    segments = [
        (
            datetime.fromisoformat("2026-01-12T09:00:00+00:00"),
            _display(1) + _cycle(rng, wash_level=170, heat=17, wash=60, rinse=44),
        ),
        (
            datetime.fromisoformat("2026-01-13T13:30:00+00:00"),
            _standby(rng, 30)
            + _display(2)
            + _cycle(rng, wash_level=78, heat=11, wash=68, rinse=36),
        ),
        # Still running when the history ends.
        (
            datetime.fromisoformat("2026-01-15T18:30:00+00:00"),
            _standby(rng, 30)
            + _display(1)
            + _cycle(rng, wash_level=160, heat=17, wash=60, rinse=40)[:62],
        ),
    ]
    readings = []
    for start, powers in segments:
        for i, power in enumerate(powers):
            # Reports arrive a few milliseconds either side of every 30 s.
            jitter = timedelta(milliseconds=rng.uniform(-5, 5))
            readings.append((start + STEP * i + jitter, round(power, 2)))
    # The recorder only stores changes.
    return [r for i, r in enumerate(readings) if i == 0 or r[1] != readings[i - 1][1]]


def _filtered(
    readings: list[tuple[datetime, float]], window: int = 4
) -> list[tuple[datetime, float]]:
    recent: deque[float] = deque(maxlen=window)
    filtered = []
    for ts, power in readings:
        recent.append(power)
        filtered.append((ts, round(sum(recent) / len(recent), 2)))
    return filtered


def _write(name: str, readings: list[tuple[datetime, float]]) -> None:
    with (HERE / name).open("w", newline="") as f:
        csv.writer(f).writerows((ts.isoformat(), power) for ts, power in readings)


def main() -> None:
    readings = _readings(random.Random(20260112))
    _write("washing_machine_raw.csv", readings)
    _write("washing_machine_filtered.csv", _filtered(readings))


if __name__ == "__main__":
    main()
