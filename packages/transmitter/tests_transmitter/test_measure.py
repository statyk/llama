"""Smoke test for scripts/measure_scheduler.py on the Task 8 fixture library."""

import importlib.util
import time
from pathlib import Path

from tests_transmitter.helpers import library_pieces
from transmitter.clock import BlockConfig, ClockConfig, OpenConfig

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "measure_scheduler.py"


def _load():
    spec = importlib.util.spec_from_file_location("measure_scheduler", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_two_weeks_on_the_fixture_library():
    ms = _load()
    clock = ClockConfig(
        timezone="America/New_York", open=OpenConfig(exclude_profiles=["dead", "funk"]),
        block=[BlockConfig(name="dead-am", start="07:00", profiles=["dead"], early_minutes=0, late_minutes=15),
               BlockConfig(name="funk-sat", start="22:30", days=["sat"], profiles=["funk"],
                           early_minutes=0, late_minutes=15)])
    t0 = time.monotonic()
    res = ms.measure(library_pieces(), clock, weeks=2)
    assert time.monotonic() - t0 < 10
    assert {"weeks", "total", "occurrences_per_week", "clock_start", "pool"} <= set(res)
    assert res["occurrences_per_week"] == 8
    assert res["total"]["block_starts"] == 2 * res["occurrences_per_week"]
    assert len(res["weeks"]) == 2
    assert sum(w["block_starts"] for w in res["weeks"]) == res["total"]["block_starts"]
    for key in ("misses", "miss_share", "fill_minutes", "bends", "repeat_gap_days", "own_profile_share"):
        assert key in res["total"]
    by = res["total"]["repeat_gap_days_by_profile"]
    assert by and all({"repeats", "min", "median", "within_7d"} <= set(v) for v in by.values())
    aired, pool_n = res["total"]["distinct_aired_by_profile"]["dead"]
    assert 0 < aired <= pool_n
