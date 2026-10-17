"""Shared fixtures."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def load_readings(name: str) -> list[tuple[datetime, float]]:
    """Readings exported from the recorder as `timestamp,watts` rows."""
    with (FIXTURES / name).open() as f:
        return [
            (datetime.fromisoformat(ts), float(power))
            for ts, power in csv.reader(f)
            if power not in ("unavailable", "unknown")
        ]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def raw_readings():
    return load_readings("washing_machine_raw.csv")


@pytest.fixture
def filtered_readings():
    return load_readings("washing_machine_filtered.csv")
