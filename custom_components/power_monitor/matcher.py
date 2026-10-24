"""Match a running cycle against recorded cycles.

Each recorded cycle is a template. The live cycle is aligned against the
start of every template with open-ended dynamic time warping (DTW), which
finds how far through each template the live cycle has got even when phases
run longer or shorter (e.g. heating on a cold day). The best aligned templates
give the program and the time remaining.

The alignment is computed one row per new sample, so each update costs
O(template length) per template rather than recomputing the whole matrix.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
import math

INF = math.inf

# Cost of the live cycle running slower or faster than the template for one
# sample. Without it, a wash phase at a different power level (e.g. a smaller
# load) aligns to whichever later phase looks closest and the estimate jumps
# ahead. Tuned on recorded washing machine cycles.
PACE_PENALTY = 2.0


def resample(
    readings: Sequence[tuple[datetime, float]],
    start: datetime,
    end: datetime,
    step: timedelta,
) -> list[float]:
    """Time-weighted average power per complete step between start and end.

    Each reading holds until the next one. Time before the first reading uses
    the first reading's value.
    """
    step_s = step.total_seconds()
    count = int((end - start).total_seconds() // step_s)
    if count <= 0 or not readings:
        return []
    totals = [0.0] * count
    limit = count * step_s
    for i, (ts, power) in enumerate(readings):
        seg_start = 0.0 if i == 0 else (ts - start).total_seconds()
        seg_end = (
            (readings[i + 1][0] - start).total_seconds()
            if i + 1 < len(readings)
            else limit
        )
        seg_start, seg_end = max(seg_start, 0.0), min(seg_end, limit)
        while seg_start < seg_end:
            bucket = int(seg_start // step_s)
            bucket_end = min((bucket + 1) * step_s, seg_end)
            totals[bucket] += power * (bucket_end - seg_start)
            seg_start = bucket_end
    return [total / step_s for total in totals]


def feature(power: float) -> float:
    """Compress power so 80 W vs 170 W matters as much as heating vs not."""
    return math.log1p(max(power, 0.0))


@dataclass(frozen=True)
class Template:
    """A recorded cycle used as a reference."""

    id: str
    program: str | None
    samples: Sequence[float]


@dataclass(frozen=True)
class TemplateMatch:
    """How well the live cycle matches one template so far."""

    template: Template
    distance: float
    position: int  # index into template.samples the live cycle is aligned to

    def remaining(self, step: timedelta) -> timedelta:
        return step * (len(self.template.samples) - 1 - self.position)


@dataclass(frozen=True)
class Estimate:
    """Best guess at the program and time remaining."""

    program: str | None
    confidence: float | None
    remaining: timedelta | None
    matches: tuple[TemplateMatch, ...]


class _Alignment:
    """Incremental open-ended DTW of the live cycle against one template."""

    def __init__(self, template: Template, band_fraction: float, min_band: int):
        self.template = template
        self._y = [feature(p) for p in template.samples]
        self._band = max(min_band, int(len(self._y) * band_fraction))
        self._row: list[float] = []
        self._n = 0

    def push(self, power: float) -> None:
        # Asymmetric steps: every live sample is matched exactly once and the
        # template advances 0-2 samples per live sample. Every path then has
        # the same number of terms, so alignments ending at different template
        # positions compare fairly without favouring longer paths.
        x = feature(power)
        y = self._y
        i = self._n
        prev = self._row
        row = [INF] * len(y)
        if i == 0:
            # Both cycles start together.
            row[0] = abs(x - y[0])
        else:
            lo = max(0, i - self._band)
            hi = min(len(y) - 1, 2 * i, i + self._band)
            for j in range(lo, hi + 1):
                best = min(
                    prev[j] + PACE_PENALTY,
                    prev[j - 1] if j else INF,
                    prev[j - 2] + PACE_PENALTY if j > 1 else INF,
                )
                if best < INF:
                    row[j] = abs(x - y[j]) + best
        self._row = row
        self._n += 1

    def best(self) -> TemplateMatch | None:
        if not self._n:
            return None
        total, j = min((total, j) for j, total in enumerate(self._row))
        if total == INF:
            # Live cycle has run past the band of this template.
            return None
        return TemplateMatch(self.template, total / self._n, j)


class CycleMatcher:
    """Align a live cycle against all templates and estimate the outcome."""

    def __init__(
        self,
        templates: Iterable[Template],
        step: timedelta,
        *,
        band_fraction: float = 0.25,
        min_band: int = 20,
        neighbours: int = 3,
        overrun_grace: int = 10,
    ) -> None:
        self.step = step
        self.samples = 0
        self._neighbours = neighbours
        # Samples the live cycle may run past a template's end before that
        # template stops counting towards the remaining time.
        self._overrun_grace = overrun_grace
        self._alignments = [
            _Alignment(t, band_fraction, min_band) for t in templates if t.samples
        ]

    def extend(self, samples: Sequence[float]) -> None:
        """Feed resampled power for the whole live cycle so far.

        Only samples not seen before are pushed, so this can be called with the
        full resampled cycle on every update.
        """
        for power in samples[self.samples :]:
            for alignment in self._alignments:
                alignment.push(power)
        self.samples = max(self.samples, len(samples))

    def matches(self) -> list[TemplateMatch]:
        found = (a.best() for a in self._alignments)
        return sorted((m for m in found if m), key=lambda m: m.distance)

    def estimate(self, program: str | None = None) -> Estimate:
        """Estimate the program and remaining time.

        With `program` set, only that program's templates are used for the
        remaining time and detection is skipped.
        """
        matches = self.matches()
        confidence = None
        if program is None:
            program, confidence = _detect_program(matches)
        # A template the live cycle has clearly outrun can only say "any moment
        # now", which stays wrong for as long as the overrun lasts.
        usable = [m for m in matches if not self._overrun(m)]
        candidates = [
            m for m in usable if program is None or m.template.program == program
        ]
        if not candidates:
            # Nothing usable recorded for this program, so use the closest of any.
            candidates = usable
        nearest = candidates[: self._neighbours]
        remaining = None
        if nearest:
            weights = [1 / (m.distance + 1e-6) for m in nearest]
            seconds = sum(
                w * m.remaining(self.step).total_seconds()
                for w, m in zip(weights, nearest, strict=True)
            ) / sum(weights)
            remaining = timedelta(seconds=round(seconds))
        return Estimate(program, confidence, remaining, tuple(nearest))

    def _overrun(self, match: TemplateMatch) -> bool:
        """Whether the live cycle has gone well past the end of the template."""
        length = len(match.template.samples)
        return (
            match.position == length - 1 and self.samples - length > self._overrun_grace
        )


def _detect_program(
    matches: Sequence[TemplateMatch],
) -> tuple[str | None, float | None]:
    """Pick the labelled program with the closest template.

    Confidence is 0 when the two best programs are equally close and tends to
    1 as the runner-up gets further away. It is None with only one program.
    """
    best: dict[str, float] = defaultdict(lambda: INF)
    for match in matches:
        if match.template.program is not None:
            best[match.template.program] = min(
                best[match.template.program], match.distance
            )
    if not best:
        return None, None
    ranked = sorted(best.items(), key=lambda item: item[1])
    if len(ranked) == 1:
        return ranked[0][0], None
    (program, first), (_, second) = ranked[0], ranked[1]
    confidence = 1 - first / second if second > 0 else 0.0
    return program, round(confidence, 2)
