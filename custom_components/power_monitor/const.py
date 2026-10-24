"""Constants for Power Monitor."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "power_monitor"

CONF_POWER_ENTITY = "power_entity"
CONF_PROGRAMS = "programs"
CONF_START_POWER = "start_power"
CONF_START_DELAY = "start_delay"
CONF_END_POWER = "end_power"
CONF_END_DELAY = "end_delay"
CONF_STALE_TIMEOUT = "stale_timeout"
CONF_FINISHED_TIMEOUT = "finished_timeout"

SERVICE_FORGET_CYCLE = "forget_cycle"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_CYCLE_ID = "cycle_id"

# Washing machine defaults, from a machine that idles at ~2 W, pauses at
# ~2.5 W between drum movements for up to ~90 s, and reads 0 W once done.
DEFAULT_OPTIONS = {
    CONF_PROGRAMS: [],
    CONF_START_POWER: 15.0,  # W
    CONF_START_DELAY: 60,  # s
    CONF_END_POWER: 5.0,  # W
    CONF_END_DELAY: 5,  # min
    CONF_STALE_TIMEOUT: 5,  # min, 0 disables
    CONF_FINISHED_TIMEOUT: 60,  # min, 0 keeps finished until the next cycle
}

# Resolution cycles are recorded and matched at.
STEP = timedelta(seconds=30)

UNKNOWN_PROGRAM = "Unknown"

# A finished cycle is labelled with the detected program when it was at
# least this clear a winner and nobody picked a program during the run.
AUTO_LABEL_CONFIDENCE = 0.3

# Shorter cycles aren't recorded: they're false starts, e.g. a spike while
# buttons are pressed, rather than a program.
MIN_CYCLE_DURATION = timedelta(minutes=10)

# Recorded cycles kept per labelled program, and unlabelled cycles kept.
MAX_CYCLES_PER_PROGRAM = 10
MAX_UNLABELLED_CYCLES = 10

STORAGE_VERSION = 1
