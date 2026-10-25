from datetime import datetime, timezone

from transmitter.announce import ann_id, needed, render_time, text_for
from transmitter.clock import AnnounceConfig, BlockConfig, ClockConfig, Zone, occurrences

UTC = timezone.utc


def us(*a):
    return int((datetime(*a, tzinfo=UTC) - datetime(1970, 1, 1, tzinfo=UTC)).total_seconds()) * 1_000_000


def test_time_names_every_zone_in_order():
    assert render_time(us(2096, 10, 3, 3), AnnounceConfig()) == "11 Eastern, 8 Pacific"


def test_short12_shows_minutes_only_when_nonzero():
    assert render_time(us(2096, 10, 3, 3, 30), AnnounceConfig()) == "11:30 Eastern, 8:30 Pacific"
    assert render_time(us(2096, 10, 3, 5), AnnounceConfig()) == "1 Eastern, 10 Pacific"


def test_hm12_and_24h_format():
    z = [Zone(tz="America/New_York", label="Eastern")]
    assert render_time(us(2096, 10, 3, 3), AnnounceConfig(time_format="hm12", zones=z)) == "11:00 Eastern"
    assert render_time(us(2096, 10, 3, 3), AnnounceConfig(time_format="24h", zones=z)) == "23:00 Eastern"


def _clock(*blocks):
    return ClockConfig(timezone="America/New_York", block=[BlockConfig(**b) for b in blocks])


def test_next_and_later_texts():
    c = _clock({"name": "a", "title": "Here Comes the Funk", "start": "23:00"},
               {"name": "b", "title": "Gravel & Steel", "start": "01:00"})
    o = occurrences(c, us(2096, 10, 3, 2), us(2096, 10, 3, 8))
    i = next(n for n, v in enumerate(o) if v.block.name == "a")
    x, y = o[i], o[i + 1]
    assert y.block.name == "b" and y.nominal_iso == "2096-10-03T05:00:00.000Z"
    assert text_for("later", x, y, c.announce) == (
        "Stay tuned for Here Comes the Funk at 11 Eastern, 8 Pacific, followed by Gravel & Steel at 1 Eastern, 10 Pacific.")
    assert text_for("next", x, y, c.announce) == (
        "Coming up next, Here Comes the Funk. Then at 1 Eastern, 10 Pacific, Gravel & Steel.")


def test_ids_are_stable_for_unchanged_text():
    assert ann_id("a") == ann_id("a") != ann_id("b")
    assert len(ann_id("a")) == 12


def test_needed_skips_untitled_blocks_and_uses_one_forms():
    c = _clock({"name": "A", "title": "Alpha", "start": "10:00", "days": ["mon"]},
               {"name": "B", "start": "11:00", "days": ["mon"]},
               {"name": "C", "title": "Gamma", "start": "12:00", "days": ["mon"]},
               {"name": "D", "title": "Delta", "start": "13:00", "days": ["mon"]})
    start = us(2096, 10, 1)
    n = needed(c, start, days=7)
    by_block = {}
    for r in n:
        by_block.setdefault(r.block, set()).add(r.form)
    assert by_block["A"] == {"next_one", "later_one"}      # B follows and is untitled
    assert "B" not in by_block
    assert by_block["C"] == {"next_one", "later_one", "next", "later"}
    assert len({r.id for r in n}) == len(n)
    assert [r.nominal_iso for r in n] == sorted(r.nominal_iso for r in n)


def test_needed_excludes_occurrences_at_or_after_the_span_end():
    c = _clock({"name": "A", "title": "Alpha", "start": "10:00", "days": ["mon"]},
               {"name": "C", "title": "Gamma", "start": "12:00", "days": ["mon"]})
    start = us(2096, 10, 1)
    first = occurrences(c, start, start + 14 * 86_400_000_000)
    a = next(o for o in first if o.block.name == "A" and o.nominal_us >= start)
    # span ends exactly at A's nominal time: A is excluded; one microsecond later it is included
    names = lambda until_days: {(r.block, r.nominal_iso) for r in needed(c, start, until_days)}
    d = (a.nominal_us - start) / 86_400_000_000
    assert ("A", a.nominal_iso) not in names(d)
    assert ("A", a.nominal_iso) in names(d + 1e-6)
