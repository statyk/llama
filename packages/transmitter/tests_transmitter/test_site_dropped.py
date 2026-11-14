"""Dropped tracks (llama's manifest `dropped_tracks`) in the notes JSON and the show page."""
import json
import time
from pathlib import Path

import pytest

from tests_transmitter.helpers import build_package, make_root, set_age
from transmitter import site, station
from transmitter.station import Show

META = {"artist": "Band", "date": "2005-11-01", "venue": "Club", "city": "Lincoln, NE",
        "profile": "indie", "url": "https://archive.org/details/band2005", "lineage": "AUD"}


def _notes(manifest):
    return site.build_notes("s", manifest, None, [], META)


def _kept(n, set_="1", start=1):
    return [{"set": set_, "title": chr(64 + i), "segue": False} for i in range(start, start + n)]


def _drop(title, after, set_="1"):
    return {"title": title, "set": set_, "after_track": after}


def _html(kept, dropped):
    return site._setlist_html(kept, dropped)


@pytest.mark.parametrize("extra", [{}, {"dropped_tracks": None}, {"dropped_tracks": []}])
def test_build_notes_without_field_is_unchanged(extra):
    base = {"tracks": _kept(2), "source": {"url": None}}
    assert _notes({**base, **extra}) == _notes(base)
    assert "dropped" not in _notes({**base, **extra})


def test_build_notes_lists_valid_entries():
    row = {"title": "Tuning", "duration_sec": 41.0, "set": "1", "after_track": 2,
           "source_file": "x.mp3", "reason": "junk"}
    notes = _notes({"tracks": _kept(3), "dropped_tracks": [row, {**row, "title": "Banter", "after_track": 0}]})
    assert notes["dropped"] == [{"title": "Tuning", "set": "1", "after_track": 2},
                                {"title": "Banter", "set": "1", "after_track": 0}]
    assert notes["setlist"] == [{"set": "1", "title": t, "segue": False} for t in "ABC"]


@pytest.mark.parametrize("bad", ["Tuning", {"title": "Tuning", "after_track": 1}, 7, True])
def test_build_notes_damaged_dropped_tracks_field(bad):
    assert "dropped" not in _notes({"tracks": _kept(1), "dropped_tracks": bad})


def test_build_notes_damaged_dropped_tracks_entries():
    good = _drop("Good", 1)
    bad = ["Tuning", None, 3, {}, {"title": "NoAfter"}, {"after_track": 1},
           {"title": "", "after_track": 1}, {"title": 5, "after_track": 1},
           {"title": "T", "after_track": True}, {"title": "T", "after_track": False},
           {"title": "T", "after_track": -1}, {"title": "T", "after_track": "3"},
           {"title": "T", "after_track": 1.0}, {"title": "T", "after_track": None}]
    notes = _notes({"tracks": _kept(2), "dropped_tracks": [*bad, good]})
    assert notes["dropped"] == [good]
    assert "dropped" not in _notes({"tracks": _kept(2), "dropped_tracks": bad})


def test_setlist_html_unchanged_without_dropped():
    kept = _kept(2) + _kept(2, "2", 3)
    plain = site._setlist_html(kept)
    assert _html(kept, ()) == plain == _html(kept, []) == _html(kept, [{"title": "", "after_track": 1}])
    assert plain == ('<p class="kick">Set 1</p>\n<ol><li>A</li><li>B</li></ol>\n'
                     '<p class="kick">Set 2</p>\n<ol><li>C</li><li>D</li></ol>')
    assert _html([], ()) == "<p>No setlist.</p>"


def test_struck_entry_inline_and_not_counted():
    assert _html(_kept(3), [_drop("Tuning", 2)]) == (
        '<ol><li>A</li><li>B</li><li class="dropped"><s>Tuning</s></li><li value="3">C</li></ol>')


def test_struck_entry_at_start_joins_first_group():
    kept = _kept(1) + _kept(1, "2", 2)
    assert _html(kept, [_drop("Tuning", 0, "2")]) == (
        '<p class="kick">Set 1</p>\n<ol><li class="dropped"><s>Tuning</s></li><li value="1">A</li></ol>\n'
        '<p class="kick">Set 2</p>\n<ol><li>B</li></ol>')


def test_struck_after_last_set_joins_last_group():
    kept = _kept(1) + _kept(1, "2", 2)
    out = _html(kept, [_drop("Tail", 2, "e")])
    assert out.endswith('<ol><li>B</li><li class="dropped"><s>Tail</s></li></ol>')
    assert out.count("<ol>") == 2


def test_struck_at_a_group_boundary_joins_the_earlier_group():
    kept = _kept(1) + _kept(1, "2", 2)
    out = _html(kept, [_drop("Gap", 1)])
    assert '<ol><li>A</li><li class="dropped"><s>Gap</s></li></ol>' in out
    assert '<ol><li>B</li></ol>' in out


def test_after_track_beyond_count_appends():
    assert _html(_kept(2), [_drop("Late", 99)]) == (
        '<ol><li>A</li><li>B</li><li class="dropped"><s>Late</s></li></ol>')


def test_only_struck_entries():
    assert _html([], [_drop("One", 0), _drop("Two", 5, "2")]) == (
        '<ol><li class="dropped"><s>One</s></li><li class="dropped"><s>Two</s></li></ol>')


def test_several_at_one_position_keep_input_order_and_numbering_follows_in_group():
    out = _html(_kept(3), [_drop("X", 1), _drop("Y", 1), _drop("Z", 0)])
    assert out == ('<ol><li class="dropped"><s>Z</s></li><li value="1">A</li>'
                   '<li class="dropped"><s>X</s></li><li class="dropped"><s>Y</s></li>'
                   '<li value="2">B</li><li value="3">C</li></ol>')


def test_numbering_restarts_per_group():
    kept = _kept(2) + _kept(2, "2", 3)
    out = _html(kept, [_drop("X", 3, "2")])
    assert '<ol><li>C</li><li class="dropped"><s>X</s></li><li value="2">D</li></ol>' in out
    assert '<ol><li>A</li><li>B</li></ol>' in out


def test_struck_title_is_escaped():
    assert "<s>A &lt;b&gt; &amp; c</s>" in _html(_kept(1), [_drop("A <b> & c", 1)])


def test_show_page_renders_struck_entries_and_notes_round_trip():
    template = (Path(__file__).parents[3] / "antenna" / "templates" / "show.html").read_text()
    manifest = {"tracks": _kept(3), "source": {"url": None}, "dropped_tracks": [_drop("Tuning", 2)]}
    notes = json.loads(json.dumps(_notes(manifest)))
    page = site.render_show_page(template, notes, site_url="https://r.example.org", station_name="R")
    assert '<li class="dropped"><s>Tuning</s></li><li value="3">C</li>' in page


@pytest.mark.parametrize("form", ["absent", None, [], [_drop("Tuning", 1)], "garbage"])
def test_package_eligibility_with_each_form(tmp_path, form):
    pkg = build_package(make_root(tmp_path))
    manifest = json.loads((pkg / "manifest.json").read_text())
    if form != "absent":
        manifest["dropped_tracks"] = form
        (pkg / "manifest.json").write_text(json.dumps(manifest))
    set_age(pkg, 3600.0)
    assert isinstance(station.evaluate(pkg, now_s=time.time(), quiet_s=600.0), Show)
