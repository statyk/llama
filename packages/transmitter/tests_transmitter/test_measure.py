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


NAIVE = Path(__file__).resolve().parents[3] / "docs" / "superpowers" / "2026-10-25-scheduler-measurement" / "naive_filler.py"


def _load_naive():
    spec = importlib.util.spec_from_file_location("naive_filler", NAIVE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _cache(path, **over):
    import pickle
    key = {"root": "/r", "library": "delivered", "pause_samples": 33075, "extra": 1, "pool": library_pieces()[:3]}
    key.update(over)
    path.write_bytes(pickle.dumps(key))


def test_measure_scan_cache_refuses_a_mismatch(tmp_path):
    import pytest
    ms = _load()
    c = tmp_path / "c.pkl"
    _cache(c)
    assert len(ms.load_pool(Path("/r"), "delivered", pause_samples=33075, extra=1, scan_cache=c)) == 3
    for kw in (dict(library="eligible"), dict(pause_samples=1), dict(extra=2)):
        args = dict(library="delivered", pause_samples=33075, extra=1) | kw
        with pytest.raises(SystemExit):
            ms.load_pool(Path("/r"), args.pop("library"), scan_cache=c, **args)
    with pytest.raises(SystemExit):
        ms.load_pool(Path("/other"), "delivered", pause_samples=33075, extra=1, scan_cache=c)


def test_naive_scan_cache_refuses_a_mismatch(tmp_path):
    import pytest
    nf = _load_naive()
    c = tmp_path / "c.pkl"
    _cache(c)
    shows, _ = nf.load_shows(Path("/r"), c, extra=1, pause_samples=33075)
    assert len(shows) == 3
    with pytest.raises(SystemExit):
        nf.load_shows(Path("/other"), c, extra=1, pause_samples=33075)
    with pytest.raises(SystemExit):
        nf.load_shows(Path("/r"), c, extra=2, pause_samples=33075)
