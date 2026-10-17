# Changelog

## 0.1.1

### Fixed

- **Cycles with drum pauses are now detected.** A start needed power above the start power continuously for the whole start delay. In a wash phase the drum pauses at ~2.5 W every minute or so, which reset that timer, so a wash already in that phase was never picked up (for example after setting the integration up mid-wash). Short dips no longer cancel a start; it's only cancelled once power stays low for the full start delay.
- **Partial cycles are no longer learned from.** A cycle only counts as seen from its start when the appliance was quiet for at least the end delay beforehand. One joined part way through is still shown as running, but gets no end estimate and isn't recorded, since it would teach the wrong length and shape.
- **Very short cycles are ignored.** Runs under 10 minutes, such as a spike while pressing buttons, aren't recorded.

### Added

- `start_observed` attribute on the cycle start sensor. When `false`, the start time is when the integration noticed the cycle rather than when it began.

## 0.1.0

First release.

- Detects appliance cycles from a power sensor, with configurable start and end thresholds and delays.
- Handles smoothing filter sensors that hold their last value after the appliance switches off, by treating a sensor that stops updating as 0 W.
- Records finished cycles and matches the running cycle against them to estimate the end time and detect the program.
- Program select to override the detected program during a run or label a cycle afterwards.
- Entities per appliance: state, running, cycle start, estimated end (with remaining minutes and progress), detected program.
