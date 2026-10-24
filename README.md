# Power Monitor

A Home Assistant custom integration that watches an appliance's power sensor. It detects when a cycle starts and finishes, works out which program is running, and estimates when the cycle will end.

You add one entry per appliance. Each entry creates a device with:

| Entity | Shows |
|---|---|
| `sensor.<name>_state` | `idle` / `running` / `finished` |
| `binary_sensor.<name>_running` | on while a cycle runs |
| `sensor.<name>_cycle_start` | start of the running cycle, or the last one |
| `sensor.<name>_estimated_end` | estimated end, or when the last cycle ended. Attributes: `remaining_minutes`, `progress`, `matched_cycles` |
| `sensor.<name>_detected_program` | program of the running or last cycle. Attributes: `source`, `confidence` |
| `select.<name>_program` | set it during a run to override detection, or after a run to label it |
| `sensor.<name>_recorded_cycles` | (diagnostic) number of recorded cycles. Attribute `cycles` lists each one's `id`, `program`, `start` and `minutes` |

## How it works

1. **Readings**: readings above *maximum power* (default 3,500 W) or below 0 W are ignored as glitches. This lets you use a plug's raw sensor without a smoothing filter in front of it.
2. **Detection** (`detector.py`): a cycle starts once power has been at or above *start power* for *start delay*. Dips shorter than the start delay, like drum pauses, don't reset it. It ends when power stays below *end power* for *end delay*. If the sensor sends nothing for the *no-update timeout*, power is treated as 0 W from its last update. This is needed because smoothing filters hold their last value once the appliance switches off.
3. **Recording**: each finished cycle is stored as 30 s time-weighted averages (`.storage/power_monitor.<entry_id>`). Cycles under 10 minutes aren't recorded. Neither are cycles already running when monitoring began, which are cycles not preceded by a quiet spell at least as long as the end delay.
4. **Matching** (`matcher.py`): while a cycle runs, it is compared against the start of every recorded cycle using open-ended dynamic time warping. This finds how far through each recorded cycle the current one has got, even when phases run longer or shorter. The closest recorded cycles give the remaining time. The closest labelled ones give the program.
5. **Labelling**: pick a program in the select during a run or after it. A cycle with no program picked is labelled with the detected program only when that program clearly beats the next closest one.

You need at least one recorded cycle before end times are estimated, and at least one labelled cycle per program before that program can be detected.

## Install

### HACS

1. In HACS, open the menu → **Custom repositories**, add `https://github.com/pmaciocia/power-monitor` with type **Integration**.
2. Download **Power Monitor** and restart Home Assistant.

### Manually

Copy `custom_components/power_monitor` into `/config/custom_components/` and restart Home Assistant.

### Set up

Go to **Settings → Devices & services → Add integration → Power Monitor**. Thresholds and programs are under the entry's **Configure** button. To switch to a different power sensor and keep the recorded cycles, use **Reconfigure** from the entry's menu.

### Removing a bad recorded cycle

If a recorded cycle is wrong, for example cut short, delete it with the **Forget cycle** action. Get its ID from the `cycles` attribute of the Recorded cycles sensor:

```yaml
action: power_monitor.forget_cycle
data:
  config_entry_id: <entry id>
  cycle_id: 51c6524d78004d5489335fc77553ec88
```

## Development

```sh
uv sync
uv run pytest
uv run ruff check custom_components tests
```

`tests/fixtures` holds synthetic washing machine history (raw plug and filtered sensor) modelled on a real machine, which the detector and matcher tests replay. Regenerate it with `uv run python tests/fixtures/generate.py`.

## Releasing

1. Bump `version` in `custom_components/power_monitor/manifest.json` and `pyproject.toml`.
2. Add a `## <version>` section to `CHANGELOG.md` describing the changes for users.
3. Commit, then push a matching tag: `git tag -a v0.1.2 -m v0.1.2 && git push origin v0.1.2`.

The release workflow checks the tag matches the manifest, then creates the GitHub release that HACS installs from, with that version's changelog section as its notes. It fails if the section is missing.

## License

MIT
