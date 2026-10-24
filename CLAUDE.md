# CLAUDE.md

Home Assistant custom integration (`power_monitor`, distributed through HACS) that watches an appliance's power sensor. It detects cycles, records them, and matches the running cycle against recorded ones to estimate the program and end time. The README covers user-facing behaviour.

## Commands

```sh
uv sync                                    # Python 3.14 venv with the HA test harness (pinned in uv.lock)
uv run pytest                              # all tests
uv run ruff check custom_components tests
uv run ruff format custom_components tests
uv run python tests/fixtures/generate.py   # regenerate the synthetic fixtures
```

Use `uv run`, not the system `python3`.

## Layout

- `custom_components/power_monitor/detector.py`: the cycle state machine (idle, running, finished). It has **no Home Assistant imports**, so it can be replayed against recorded readings.
- `custom_components/power_monitor/matcher.py`: resampling into 30 s steps and incremental open-ended DTW matching, also free of HA imports. `PACE_PENALTY` was tuned on real washer cycles; re-check the matcher tests if you change it.
- `monitor.py`: `CycleMonitor` connects the detector and matcher to HA. It owns the state and report listeners, the 30 s tick, the `Store` persistence (recorded cycles plus the in-progress cycle) and program labelling. Entities subscribe through `async_add_listener`.
- `sensor.py`, `binary_sensor.py`, `select.py`: thin entities that read from the monitor. `entity.py` holds the shared base.
- `config_flow.py`: the setup step (name, power sensor, programs), a reconfigure step to change the power sensor, and an options flow for thresholds. Changing options reloads the entry.
- `__init__.py`: entry setup, plus the `forget_cycle` action. The action is registered in `async_setup`, not per entry, and is described in `services.yaml`.
- `tests/replay.py`: feeds readings to the detector with 30 s ticks in between, the way the monitor does. `tests/test_init.py` runs end to end in HA using `freezer` and `async_fire_time_changed`.

## Things that matter

- **Keep detector and matcher free of HA imports.** HA code belongs in `monitor.py` and the entity files.
- **Listen for state *reported* events as well as state changes.** HA doesn't fire a state change when a sensor repeats the same value. Without state reported events, a steady load would look like a silent sensor and trip the stale timeout.
- **Smoothing `filter` sensors hold their last value** after the source stops changing. The `stale_timeout` option (no updates means 0 W from the last update) is there for them.
- **Duty-cycled loads.** Washing machines pause the drum at ~2.5 W for 30 s or so mid-wash. A start is only cancelled by a dip as long as the start delay, and a cycle only ends after the end delay below the end power.
- **Only learn from complete cycles.** A cycle is recorded only if it followed a quiet spell of at least the end delay (`Cycle.observed_start`) and ran for at least `MIN_CYCLE_DURATION`. Cycles joined part way get no estimate.
- **Every new string goes in both `strings.json` and `translations/en.json`**, which are kept identical. Hassfest also requires a `description` on each config step. Write literal text: `[%key:...%]` references are only resolved for core integrations.
- **Stored data must load in older shapes.** Fields added to `.storage` (the cycle list or the in-progress cycle) need a safe default when missing. Choose the default that avoids learning from bad data, not the convenient one.
- **Test fixtures must stay synthetic.** Never commit real recorder exports, because they reveal when the owner uses the appliance. Model new scenarios in `tests/fixtures/generate.py`.

## Releasing

1. Bump `version` in `custom_components/power_monitor/manifest.json` and `pyproject.toml`, then run `uv lock`.
2. Add a `## <version>` section to `CHANGELOG.md` with user-facing notes. The release workflow publishes it as the release notes and fails without it.
3. Commit, push, then `git tag -a vX.Y.Z -m vX.Y.Z && git push origin vX.Y.Z`.

CI (`.github/workflows/validate.yml`) runs HACS validation, hassfest, ruff and pytest on every push.
