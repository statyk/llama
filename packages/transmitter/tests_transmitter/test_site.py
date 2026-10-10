import json
from pathlib import Path

from tests_transmitter.helpers import build_package, make_root
from transmitter import aacenc, grid, site
from transmitter.analysis import FileAnalysis, ShowAnalysis
from transmitter.layout import PlanRow
from transmitter.workspace import Epoch

EPOCH = Epoch("e1", grid.iso_to_us("2026-10-10T00:00:00Z"))
TEMPLATE = (Path(__file__).resolve().parents[3] / "antenna" / "templates" / "show.html").read_text()
META = {"artist": "Band", "date": "2005-11-01", "venue": "Club", "city": "Lincoln, NE",
        "profile": "indie", "url": "https://archive.org/details/band2005", "lineage": "AUD"}


def _analysis(key):
    files = (FileAnalysis("dj-audio/i.mp3", "clip", "DJ intro (set 1)", 44_100),
             FileAnalysis("audio/01.mp3", "track", "Song 1", 441_000),
             FileAnalysis("dj-audio/o.mp3", "clip", "DJ outro", 44_100))
    return ShowAnalysis(key, f"show-{key}", files, -18.0, -2.0, META)


def _row(seq, key, start_frame, frames=1000, **kw):
    return PlanRow(seq=seq, slug=f"show-{key}", dir=f"show-{key}", key=key, start_frame=start_frame,
                   frames=frames, **kw)


def test_file_starts_follow_actual_frame_positions_plus_encoder_priming():
    row = _row(0, "a", 441 * 10)
    starts = site.file_starts(row, _analysis("a"), 33_075, EPOCH)
    base = 441 * 10 * 1024 + aacenc.ENCODER_PRIMING_SAMPLES
    assert starts[0] == {"kind": "clip", "title": "DJ intro (set 1)",
                         "start": grid.us_to_iso(EPOCH.epoch_us + grid.samples_to_us(base))}
    assert starts[1]["start"] == grid.us_to_iso(EPOCH.epoch_us + grid.samples_to_us(base + 44_100 + 33_075))


def test_file_starts_stop_at_a_cut():
    row = _row(0, "a", 0, frames=1000, cut_frame=40)       # cut after ~0.93 s
    assert [f["title"] for f in site.file_starts(row, _analysis("a"), 33_075, EPOCH)] == ["DJ intro (set 1)"]


def test_timeline_window_and_recent():
    rows = [_row(0, "a", 0), _row(1, "b", 1087), _row(2, "c", 2174)]
    analyses = {k: _analysis(k) for k in "abc"}
    now = EPOCH.epoch_us + grid.frame_to_us(1500)          # inside b
    last_n = 3                                             # published through frame 1764
    tl = site.build_timeline(rows, analyses, EPOCH, now_us=now, last_n=last_n, pause_samples=33_075)
    assert [s["slug"] for s in tl["shows"]] == ["show-a", "show-b"]     # c starts after the horizon
    assert tl["recent"] == ["show-a"]
    assert tl["anchors"] == [] and tl["epoch_id"] == "e1"
    a = tl["shows"][0]
    assert a["start"] == EPOCH.iso and a["notes"] == "notes/show-a.json" and a["page"] == "show/show-a.html"
    assert a["artist"] == "Band"


def test_timeline_skips_rows_without_analysis():
    tl = site.build_timeline([_row(0, "a", 0)], {}, EPOCH, now_us=EPOCH.epoch_us, last_n=5, pause_samples=0)
    assert tl["shows"] == []


def test_airtimes():
    rows = [_row(0, "a", 0), _row(1, "b", 1087), _row(2, "a", 2174)]
    got = site.airtimes(rows, "show-a", EPOCH, EPOCH.epoch_us, EPOCH.epoch_us + 10**12)
    assert [g["start"] for g in got] == [EPOCH.iso, grid.us_to_iso(EPOCH.epoch_us + grid.frame_to_us(2174))]


def test_notes_from_a_package(tmp_path):
    pkg = build_package(make_root(tmp_path))
    manifest, briefing = site.read_package_notes(pkg)
    notes = site.build_notes(pkg.name, manifest, briefing, [], META)
    assert notes["artist"] == "Band" and notes["url"] == "https://archive.org/details/band2005"
    assert notes["setlist"][0] == {"set": "1", "title": "Song 1", "segue": False}
    assert notes["briefing"].startswith("A fine show.")


def test_notes_fall_back_to_cached_meta_when_the_package_is_unreadable(tmp_path):
    assert site.read_package_notes(tmp_path / "gone") == (None, None)
    notes = site.build_notes("s", None, None, [], META)
    assert notes["artist"] == "Band" and notes["setlist"] == [] and notes["briefing"] == ""


def test_show_page_escapes_and_fills_every_placeholder():
    notes = site.build_notes("s", None, "Para <script>alert(1)</script> one.\n\nPara two.", [], META)
    html = site.render_show_page(TEMPLATE, notes, site_url="https://radio.example.org/", station_name="llama radio")
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
    assert '<meta property="og:url" content="https://radio.example.org/show/s.html">' in html
    assert '<meta property="og:title" content="Band — 2005-11-01">' in html
    assert "<p>Para two.</p>" in html
    assert "$" not in html.split("<script>")[0]            # no unfilled placeholder


def test_a_non_utf8_briefing_is_an_unreadable_briefing(tmp_path):
    pkg = build_package(make_root(tmp_path))
    (pkg / "briefing.md").write_bytes(b"\xff\xfe not utf-8 \x80")
    manifest, briefing = site.read_package_notes(pkg)
    assert manifest is not None and briefing is None


def test_a_non_dict_briefing_field_is_an_unreadable_briefing(tmp_path):
    pkg = build_package(make_root(tmp_path))
    data = json.loads((pkg / "manifest.json").read_text())
    data["briefing"] = "briefing.md"
    (pkg / "manifest.json").write_text(json.dumps(data))
    manifest, briefing = site.read_package_notes(pkg)
    assert manifest is not None and briefing is None


def test_null_manifest_fields_fall_back_to_cached_meta():
    manifest = {"show": {"artist": "Real", "venue": None, "city": None, "date": "2005-11-01"},
                "source": {"url": None, "lineage": None, "profile": None}}
    notes = site.build_notes("s", manifest, None, [], META)
    assert notes["artist"] == "Real" and notes["venue"] == "Club" and notes["city"] == "Lincoln, NE"
    assert notes["url"] == META["url"] and notes["lineage"] == "AUD" and notes["profile"] == "indie"


def test_cut_frame_is_an_absolute_frame_number():
    # Starts at frame 1000, cut at absolute frame 1040 (40 frames in). A relative
    # reading would put the cut at 2040 and keep every file.
    row = _row(0, "a", 1000, frames=1000, cut_frame=1040)
    got = site.file_starts(row, _analysis("a"), 33_075, EPOCH)
    assert [f["title"] for f in got] == ["DJ intro (set 1)"]
    assert site.row_span_us(row, EPOCH)[1] == EPOCH.epoch_us + grid.frame_to_us(1040)


def test_timeline_lower_bound_is_24_hours_before_now():
    day_frames = site.DAY_US // grid.frame_to_us(1)      # frames in 24 h, floor
    old = _row(0, "a", 0, frames=1000)                   # ends at frame 1000
    now = EPOCH.epoch_us + grid.frame_to_us(1000) + site.DAY_US
    rows = [old, _row(1, "b", 1000 + day_frames + 1000, frames=1000)]
    analyses = {k: _analysis(k) for k in "ab"}
    # "a" ends exactly 24 h before now: excluded; "b" is inside the window.
    tl = site.build_timeline(rows, analyses, EPOCH, now_us=now, last_n=10_000, pause_samples=0)
    assert [s["slug"] for s in tl["shows"]] == ["show-b"]
    just_in = site.build_timeline(rows, analyses, EPOCH, now_us=now - 1, last_n=10_000, pause_samples=0)
    assert [s["slug"] for s in just_in["shows"]] == ["show-a", "show-b"]


def test_recent_is_capped_at_ten_newest_first():
    rows = [_row(i, f"k{i}", i * 1000, frames=1000) for i in range(12)]
    analyses = {f"k{i}": _analysis(f"k{i}") for i in range(12)}
    now = EPOCH.epoch_us + grid.frame_to_us(12 * 1000)    # all twelve have ended
    tl = site.build_timeline(rows, analyses, EPOCH, now_us=now, last_n=10_000, pause_samples=0)
    assert tl["recent"] == [f"show-k{i}" for i in range(11, 1, -1)]
