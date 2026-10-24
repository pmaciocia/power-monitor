# Changelog

## 0.1.3

### Added

- **Maximum power** setting (default 3,500 W). Readings above it, and any below 0 W, are ignored as glitches, so they never reach detection or recorded cycles. Some plugs occasionally report garbage such as 107,374,182.4 W. You can now use a plug's raw power sensor directly instead of a smoothing filter. Smoothing filters lag and can hold their last value after the appliance switches off. Set it to 0 to turn it off.

## 0.1.2

### Fixed

- **A cycle joined part way could still be learned from after upgrading to 0.1.1.** A cycle in progress during the upgrade had been saved by 0.1.0 without the "seen from its start" flag, and 0.1.1 assumed it was. It is now treated as joined part way. If an earlier cycle was recorded this way, remove it with the new **Forget cycle** action.
- **The estimate no longer sits at "any moment now" after a cycle outruns the recorded ones.** Once the running cycle is more than 5 minutes past the end of a recorded cycle, that recorded cycle stops counting towards the remaining time. If none are left, the estimated end shows as unknown rather than now.
- **Choosing a program after a cycle that wasn't recorded no longer relabels an older cycle.** After a short or part-way cycle, the program select shows Unknown and leaves the recorded cycles alone.

### Added

- **Forget cycle** action (`power_monitor.forget_cycle`) to delete a recorded cycle that was cut short or mislabelled.
- **Recorded cycles** diagnostic sensor: the number of recorded cycles, with each one's ID, program, start and length in its `cycles` attribute.
- **Reconfigure** option to change an appliance's power sensor without losing its recorded cycles, e.g. to move from a smoothed sensor to the raw one.

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
