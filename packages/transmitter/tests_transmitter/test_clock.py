from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from transmitter.clock import (
    IMPLICIT_CLOCK,
    BlockConfig,
    ClockConfig,
    Occurrence,
    live_clock,
    load_clock,
    occurrences,
)
from transmitter.errors import ConfigError
from transmitter.workspace import Workspace

NY = ZoneInfo("America/New_York")
UTC = timezone.utc
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def us(dt):
    return (dt.astimezone(UTC) - EPOCH) // timedelta(microseconds=1)


def starting(occ, from_us):
    return [o for o in occ if o.nominal_us >= from_us]


def clock(*blocks, tz="America/New_York"):
    return ClockConfig(timezone=tz, block=[BlockConfig(**b) for b in blocks])


VALID = 'timezone = "America/New_York"\n\n[[block]]\nname = "a"\nstart = "19:00"\n'


def write(tmp_path, text, name="clock.toml"):
    p = tmp_path / name
    p.write_text(text)
    return p


def test_weekday_rotation_expands_by_day():
    c = clock(
        {"name": "funk", "days": ["mon"], "start": "22:00"},
        {"name": "southern", "days": ["tue", "wed", "thu", "fri", "sat", "sun"], "start": "22:00"},
    )
    start = us(datetime(2027, 1, 4, 0, 0, tzinfo=NY))  # a Monday
    occ = starting(occurrences(c, start, start + 7 * 86400 * 1_000_000 - 1), start)
    assert len(occ) == 7
    assert all(o.nominal_us == us(datetime(2027, 1, 4 + i, 22, 0, tzinfo=NY)) for i, o in enumerate(occ))
    assert [o.block.name for o in occ] == ["funk"] + ["southern"] * 6


def test_block_runs_to_the_next_start_across_midnight():
    c = clock({"name": "eve", "start": "19:00"}, {"name": "late", "start": "02:00"})
    start = us(datetime(2027, 1, 4, 0, 0, tzinfo=NY))
    occ = occurrences(c, start, start + 86400 * 1_000_000)
    eve = [o for o in starting(occ, start) if o.block.name == "eve"][0]
    assert eve.end_us == us(datetime(2027, 1, 5, 2, 0, tzinfo=NY))


def test_spring_forward_collapses_and_drops():
    c = clock({"name": "a", "start": "02:30"}, {"name": "b", "start": "03:00"})
    start = us(datetime(2027, 3, 14, 0, 0, tzinfo=UTC))
    occ = occurrences(c, start, start + 86400 * 1_000_000)
    day = [o for o in occ if o.local_date.isoformat() == "2027-03-14"]
    assert len(day) == 1
    assert day[0].nominal_us == us(datetime(2027, 3, 14, 7, 0, tzinfo=UTC))
    assert day[0].block.name == "b"


def test_fall_back_ambiguous_uses_first_occurrence():
    c = clock({"name": "a", "start": "01:30"})
    start = us(datetime(2027, 11, 7, 0, 0, tzinfo=UTC))
    occ = starting(occurrences(c, start, start + 86400 * 1_000_000), start)
    assert occ[0].nominal_us == us(datetime(2027, 11, 7, 5, 30, tzinfo=UTC))


def test_asymmetric_window():
    c = clock({"name": "a", "start": "19:00", "early_minutes": 0, "late_minutes": 15})
    start = us(datetime(2027, 1, 4, 0, 0, tzinfo=NY))
    o = starting(occurrences(c, start, start + 86400 * 1_000_000), start)[0]
    assert o.lo_us == o.nominal_us
    assert o.hi_us == o.nominal_us + 15 * 60 * 1_000_000


def test_symmetric_window_and_iso_key():
    c = clock({"name": "a", "start": "19:00"})
    start = us(datetime(2027, 1, 4, 0, 0, tzinfo=NY))
    o = starting(occurrences(c, start, start + 86400 * 1_000_000), start)[0]
    assert o.nominal_us - o.lo_us == o.hi_us - o.nominal_us == 15 * 60 * 1_000_000
    assert o.key == ("a", "2027-01-05T00:00:00.000Z")
    assert o.nominal_iso == o.key[1]


def test_span_intersection_includes_running_block():
    c = clock({"name": "a", "start": "19:00"})
    mid = us(datetime(2027, 1, 5, 12, 0, tzinfo=NY))
    occ = occurrences(c, mid, mid + 1)
    assert len(occ) == 1 and occ[0].nominal_us == us(datetime(2027, 1, 4, 19, 0, tzinfo=NY))


def test_minimal_clock_loads_with_defaults(tmp_path):
    c = load_clock(write(tmp_path, VALID))
    assert c.wiggle_minutes == 15
    assert c.announce.next == "Coming up next, {title}. Then at {next_time}, {next_title}."
    assert c.announce.time_format == "short12"
    assert [z.label for z in c.announce.zones] == ["Eastern", "Pacific"]
    assert c.rotation.concert_gap_days == 45 and c.rotation.on_this_day_weight == 3.0
    assert c.open.exclude_profiles == []


def bad(tmp_path, text):
    with pytest.raises(ConfigError) as e:
        load_clock(write(tmp_path, text))
    assert "clock.toml" in str(e.value)


HEAD = 'timezone = "America/New_York"\n'
BLK = '[[block]]\nname = "a"\nstart = "19:00"\n'


def test_duplicate_day_and_start_is_a_config_error(tmp_path):
    bad(tmp_path, HEAD + BLK + '[[block]]\nname = "b"\nstart = "19:00"\n')


def test_unique_names_and_disjoint_days_ok_and_dup_names_error(tmp_path):
    bad(tmp_path, HEAD + BLK + '[[block]]\nname = "a"\nstart = "20:00"\n')
    load_clock(write(tmp_path, HEAD + BLK.replace('start', 'days = ["mon"]\nstart') +
                     '[[block]]\nname = "b"\ndays = ["tue"]\nstart = "19:00"\n'))


def test_unknown_key_is_a_config_error(tmp_path):
    bad(tmp_path, HEAD + "bogus = 1\n" + BLK)
    bad(tmp_path, HEAD + BLK + "bogus = 1\n")
    bad(tmp_path, HEAD + "[announce]\nbogus = 1\n" + BLK)


def test_bad_timezone_and_no_blocks(tmp_path):
    bad(tmp_path, 'timezone = "Mars/Base"\n' + BLK)
    bad(tmp_path, HEAD)
    bad(tmp_path, HEAD + '[announce]\nzones = [{tz = "Nope/Zone", label = "x"}]\n' + BLK)
    bad(tmp_path, HEAD + BLK.replace("19:00", "25:00"))


def test_wiggle_and_early_late_together_is_an_error(tmp_path):
    bad(tmp_path, HEAD + BLK + "wiggle_minutes = 5\nearly_minutes = 1\nlate_minutes = 1\n")
    bad(tmp_path, HEAD + BLK + "early_minutes = 1\n")


def test_bad_template_is_a_config_error(tmp_path):
    bad(tmp_path, HEAD + '[announce]\nnext = "Up {titel}"\n' + BLK)
    bad(tmp_path, HEAD + '[announce]\nnext = "Up { oops"\n' + BLK)
    bad(tmp_path, HEAD + '[announce]\nlater_one = "Up {}"\n' + BLK)


def test_one_block_form_cannot_name_next(tmp_path):
    bad(tmp_path, HEAD + '[announce]\nnext_one = "Up {next_title}"\n' + BLK)
    bad(tmp_path, HEAD + '[announce]\nlater_one = "Up {next_time}"\n' + BLK)


def test_zero_window_is_a_config_error(tmp_path):
    bad(tmp_path, HEAD + BLK + "wiggle_minutes = 0\n")
    bad(tmp_path, HEAD + BLK + "early_minutes = 0\nlate_minutes = 0\n")


def test_empty_days_is_a_config_error(tmp_path):
    bad(tmp_path, HEAD + BLK + "days = []\n")


def test_prefer_validation(tmp_path):
    ok = HEAD + BLK + 'prefer = [{ years = "1972-1977", weight = 1.5 }, { on_this_day = 5 }]\n'
    assert len(load_clock(write(tmp_path, ok)).block[0].prefer) == 2
    bad(tmp_path, HEAD + BLK + 'prefer = [{ years = "72" }]\n')
    bad(tmp_path, HEAD + BLK + 'prefer = [{ years = "1972", on_this_day = 2 }]\n')
    bad(tmp_path, HEAD + BLK + "prefer = [{ weight = 2 }]\n")


def test_live_clock_prefers_file_and_saves_last_good(tmp_path):
    ws = Workspace(tmp_path)
    ws.clock_path.write_text(VALID)
    lc = live_clock(ws)
    assert lc.source == "clock" and lc.problem is None
    assert ws.clock_last_good_path.read_text() == VALID


def test_live_clock_save_false_writes_nothing(tmp_path):
    ws = Workspace(tmp_path)
    ws.clock_path.write_text(VALID)
    assert live_clock(ws, save=False).source == "clock"
    assert not ws.clock_last_good_path.exists()


def test_invalid_clock_falls_back_to_last_good(tmp_path):
    ws = Workspace(tmp_path)
    ws.clock_path.write_text(VALID)
    live_clock(ws)
    ws.clock_path.write_text("block = 3")
    lc = live_clock(ws)
    assert lc.source == "last-good" and "clock.toml" in lc.problem
    assert lc.clock.block[0].name == "a"
    assert ws.clock_last_good_path.read_text() == VALID


def test_invalid_clock_with_no_copy_is_implicit(tmp_path):
    ws = Workspace(tmp_path)
    ws.clock_path.write_text("block = 3")
    lc = live_clock(ws)
    assert lc.source == "implicit" and lc.problem
    assert lc.clock == IMPLICIT_CLOCK


def test_no_clock_file_is_implicit_without_problem(tmp_path):
    lc = live_clock(Workspace(tmp_path))
    assert lc.source == "implicit" and lc.problem is None


def test_corrupt_last_good_is_implicit(tmp_path):
    ws = Workspace(tmp_path)
    ws.clock_path.write_text("block = 3")
    ws.clock_last_good_path.write_text("garbage = =")
    assert live_clock(ws).source == "implicit"


def test_implicit_clock_covers_everything():
    start = us(datetime(2027, 1, 4, 3, 0, tzinfo=NY))
    occ = occurrences(IMPLICIT_CLOCK, start, start + 1)
    assert len(occ) == 1 and occ[0].block.name == "open" and occ[0].is_open
    assert occ[0].max_shows is None
    assert occ[0].hi_us - occ[0].lo_us == 24 * 3600 * 1_000_000


def test_open_block_is_unbounded_profile_block_defaults_to_two():
    c = clock({"name": "o", "start": "01:00"},
              {"name": "p", "start": "02:00", "profiles": ["dead"]},
              {"name": "q", "start": "03:00", "profiles": ["dead"], "max_shows": 5})
    start = us(datetime(2027, 1, 4, 0, 0, tzinfo=NY))
    o, p, q = starting(occurrences(c, start, start + 4 * 3600 * 1_000_000), start)[:3]
    assert (o.max_shows, p.max_shows, q.max_shows) == (None, 2, 5)
    assert o.is_open and not p.is_open
    with pytest.raises(Exception):
        BlockConfig(name="x", start="01:00", max_shows=0)
