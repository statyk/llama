import json
from pathlib import Path

import pytest

from tests_transmitter.helpers import build_package, make_root
from transmitter import aacenc, grid, site
from transmitter.analysis import FileAnalysis, ShowAnalysis
from transmitter.layout import PlanRow
from transmitter.workspace import Epoch

EPOCH = Epoch("e1", grid.iso_to_us("2026-10-10T00:00:00Z"))
REPO = Path(__file__).resolve().parents[3]
TEMPLATE = (REPO / "antenna" / "templates" / "show.html").read_text()
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
    assert notes["briefing"] == briefing
    assert notes["sections"] == site.parse_briefing(notes["briefing"])


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
    assert 'data-slug="s"' in html
    assert ">Band</h2>" in html and "Club, Lincoln, NE" in html
    assert "TUE NOV 1" in html and ">2005</b>" in html
    assert "https://archive.org/details/band2005" in html and "AUD" in html
    assert "$" not in html                                 # no unfilled placeholder


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


@pytest.mark.parametrize("file_ref", [5, ["briefing.md"], {"name": "briefing.md"}, True])
def test_a_non_string_briefing_file_is_an_unreadable_briefing(tmp_path, file_ref):
    pkg = build_package(make_root(tmp_path))
    data = json.loads((pkg / "manifest.json").read_text())
    data["briefing"]["file"] = file_ref
    (pkg / "manifest.json").write_text(json.dumps(data))
    manifest, briefing = site.read_package_notes(pkg)
    assert manifest is not None and briefing is None


def test_timeline_lists_no_interstitial_rows():
    rows = [_row(0, "a", 0), _row(1, "b", 1087, kind="interstitial")]
    analyses = {k: _analysis(k) for k in "ab"}
    now = EPOCH.epoch_us + grid.frame_to_us(2000)
    tl = site.build_timeline(rows, analyses, EPOCH, now_us=now, last_n=5, pause_samples=0)
    assert [s["slug"] for s in tl["shows"]] == ["show-a"]
    assert tl["recent"] == ["show-a"]


BRIEFING = """# Briefing: Band — 2005-11-01, Club

## Context
Band played **Club** in Lincoln.
Second line of the paragraph.

## Set 1
- Opened hot
- Closed cold

## Cautions for the scriptwriter
- Do not say great.
"""


def test_parse_briefing_is_line_based_and_drops_title_and_cautions():
    assert site.parse_briefing(BRIEFING) == [
        {"heading": "Context", "blocks": [{"p": "Band played Club in Lincoln. Second line of the paragraph."}]},
        {"heading": "Set 1", "blocks": [{"ul": ["Opened hot", "Closed cold"]}]},
    ]


def test_cautions_cut_is_case_insensitive_and_runs_to_the_end():
    text = "## Context\nA\n\n## CAUTIONS for the host\n- x\n\n## Late\nB\n"
    assert [s["heading"] for s in site.parse_briefing(text)] == ["Context"]


def test_text_before_any_heading_has_a_null_heading():
    assert site.parse_briefing("Plain note.")[0] == {"heading": None, "blocks": [{"p": "Plain note."}]}


@pytest.mark.parametrize("text", ["", "   \n", "# Briefing: only a title\n"])
def test_empty_briefings_give_an_empty_list(text):
    assert site.parse_briefing(text) == []


def test_the_cautions_heading_literal_is_pinned():
    # The heading is llama's (brief.py render_briefing_md); transmitter cannot import it.
    assert site.CAUTIONS_PREFIX == "## cautions"


def test_notes_with_no_briefing_have_empty_sections():
    assert site.build_notes("s", None, None, [], META)["sections"] == []


@pytest.mark.parametrize("url,want", [
    ("https://archive.org/details/x", "https://archive.org/details/x"),
    ("http://archive.org/details/x", None),
    ("https://archive.org.evil.test/x", None),
    ("javascript:alert(1)", None), ("", None), (None, None),
])
def test_archive_link_is_a_literal_prefix_check(url, want):
    assert site.archive_link(url) == want


def _page(*, briefing=None, setlist=(), url=None, site_url="https://radio.example.org", **source):
    manifest = {"tracks": list(setlist), "source": {"url": url, **source}}
    notes = site.build_notes("s", manifest, briefing, [], META)
    return site.render_show_page(TEMPLATE, notes, site_url=site_url, station_name="LMA Radio")


def test_show_page_renders_sections_and_never_the_raw_marks():
    page = _page(briefing=BRIEFING)
    assert "<h2>Context</h2>" in page or ">Context<" in page
    assert "<li>Opened hot</li>" in page
    for raw in ("# Briefing", "## ", "**", "Cautions", "Do not say great"):
        assert raw not in page


def test_show_page_says_so_when_there_are_no_notes():
    assert "<p>No notes yet.</p>" in _page()


def test_show_page_description_is_the_first_non_heading_text():
    assert 'content="Band played Club in Lincoln.' in _page(briefing=BRIEFING)


def test_show_page_description_can_be_a_bullet_and_falls_back_to_the_title():
    assert '<meta property="og:description" content="Only a bullet">' in _page(briefing="## A\n- Only a bullet\n")
    assert '<meta property="og:description" content="Band — 2005-11-01">' in _page()


def test_show_page_description_stops_at_200_characters():
    assert 'content="' + "x" * 200 + '"' in _page(briefing="## A\n" + "x" * 300 + "\n")


def test_show_page_leaves_out_the_button_for_a_non_archive_url():
    page = _page(url="javascript:alert(1)")
    assert "Hear the full tape" not in page and "javascript:" not in page


def test_the_archive_button_opens_in_a_new_tab():
    assert ('<a class="btn" href="https://archive.org/details/x" target="_blank" rel="noopener">'
            "Hear the full tape on archive.org") in _page(url="https://archive.org/details/x")


def test_a_quote_in_an_archive_url_is_escaped_in_the_href():
    page = _page(url='https://archive.org/x"><script>')
    assert '"><script>' not in page and "&quot;&gt;&lt;script&gt;" in page


def test_a_quote_in_the_description_is_escaped():
    assert 'Band said &quot;hi&quot;' in _page(briefing='## A\nBand said "hi"\n')


def test_doubled_segue_marks_are_gone():
    page = _page(setlist=[{"title": "Drums / Space >", "segue": True, "set": "2"}])
    assert "Drums / Space &gt; &gt;" not in page and "Drums / Space &gt;" in page


@pytest.mark.parametrize("title,segue,want", [
    ("Song", False, "Song"), ("Song", True, "Song &gt;"), ("Song ->", False, "Song &gt;"),
    ("Song->", True, "Song &gt;"), ("Song -->", False, "Song &gt;"), ("Song>", False, "Song &gt;"),
    (None, False, "?"), ("  ", True, "?"),
])
def test_setlist_titles_follow_one_rule(title, segue, want):
    assert f"<li>{want}</li>" in _page(setlist=[{"title": title, "segue": segue, "set": "1"}])


def test_one_set_has_no_label_and_several_are_grouped_in_order():
    one = _page(setlist=[{"title": "A", "set": "1"}, {"title": "B", "set": "1"}])
    assert one.count("<ol>") == 1 and "Set 1" not in one
    many = _page(setlist=[{"title": "A", "set": "1"}, {"title": "B", "set": "1"},
                          {"title": "C", "set": "2"}, {"title": "D", "set": "encore"}])
    assert many.count("<ol>") == 3
    assert many.index("Set 1") < many.index("<li>B</li>") < many.index("Set 2") < many.index("<li>C</li>")
    assert many.index("<li>C</li>") < many.index("Encore") < many.index("<li>D</li>")


def test_a_show_with_no_setlist_says_so():
    assert "<p>No setlist.</p>" in _page()


def test_the_ai_disclaimer_is_on_the_page():
    assert "Show notes are AI generated and may contain mistakes." in _page()


def test_a_blank_lineage_leaves_its_label_out():
    assert "Taper's lineage" in _page(lineage="SBD")
    notes = dict(site.build_notes("s", None, None, [], META), lineage=None)
    assert "lineage" not in site.render_show_page(TEMPLATE, notes, site_url=None, station_name="LMA Radio")


def test_null_fields_are_never_printed():
    notes = site.build_notes("s", None, None, [], {})
    page = site.render_show_page(TEMPLATE, notes, site_url=None, station_name="LMA Radio")
    assert "None" not in page and "null" not in page


def test_the_slug_is_encoded_in_the_page_url_and_escaped_in_the_data_attribute():
    notes = dict(site.build_notes("s", None, None, [], META), slug='a b"c')
    page = site.render_show_page(TEMPLATE, notes, site_url="https://x.example", station_name="LMA Radio")
    assert 'content="https://x.example/show/a%20b%22c.html"' in page
    assert 'data-slug="a b&quot;c"' in page


def test_non_string_fields_never_stop_the_render():
    notes = dict(site.build_notes("s", None, None, [], META), artist=5, date=1977, venue=6, city=7, lineage=8)
    page = site.render_show_page(TEMPLATE, notes, site_url=None, station_name="LMA Radio")
    assert "5 — 1977" in page and "6, 7" in page


def test_og_image_needs_a_site_url():
    assert "cassette-og.png" in _page(site_url="https://x.example")
    assert "og:image" not in _page(site_url=None)


def test_og_image_is_absolute():
    assert '<meta property="og:image" content="https://x.example/assets/cassette-og.png">' \
        in _page(site_url="https://x.example/")


def test_show_page_escapes_sections():
    assert "<script>" not in _page(briefing="## A\n<script>x</script>\n")


def test_show_page_escapes_a_heading_and_a_bullet():
    page = _page(briefing="## <b>A</b>\n- <i>x</i>\n")
    assert "<b>" not in page and "<i>" not in page


def test_the_hostile_fixture_stays_text():
    hostile = json.loads((REPO / "antenna" / "e2e" / "fixtures" / "hostile.json").read_text())
    page = site.render_show_page(TEMPLATE, hostile, site_url=None, station_name="LMA Radio")
    assert "<img" not in page
    for raw in ("<script>window", "<svg", "<iframe", '<a href="javascript', "<h1 onclick", "<b>", "<i>", "<u>"):
        assert raw not in page


def test_the_template_has_no_inline_script():
    assert "<script>" not in TEMPLATE


def test_the_template_uses_the_new_look_and_links_home():
    assert 'href="/assets/radio.css"' in TEMPLATE and '<script type="module" src="/assets/show.js">' in TEMPLATE
    assert 'href="/"' in TEMPLATE and "../style.css" not in TEMPLATE
    for copy in ("LMA RADIO PRESENTS", "GEN ADM", "Liner notes"):
        assert copy in TEMPLATE


@pytest.mark.parametrize("date,want", [
    ("2008-11-01", ("SAT NOV 1", "2008")),
    ("1977-05-00", ("1977-05-00", "")),
    ("1977", ("1977", "")),
    ("2008-13-45", ("2008-13-45", "")),
    ("garbage", ("garbage", "")),
    (None, ("", "")),
    (1977, ("1977", "")),
])
def test_concert_stub_never_raises(date, want):
    assert site.concert_stub(date) == want


@pytest.mark.parametrize("date", ["0000-01-01", "2023-02-29", "2008-11-01\n"])
def test_concert_stub_gives_back_what_is_no_date(date):
    assert site.concert_stub(date) == (date, "")


@pytest.mark.parametrize("venue,city,want", [
    ("Club", "Lincoln", "Club, Lincoln"), ("Club", None, "Club"), (None, "Lincoln", "Lincoln"), (None, None, ""),
])
def test_where_line(venue, city, want):
    assert site.where_line(venue, city) == want


def test_parse_briefing_drops_the_bare_see_cautions_pointer():
    text = ("## Set 1\n"
            "The tape is missing a chunk of this pairing (see cautions).\n"
            "- Dark Star (See Cautions) runs long\n"
            "- Wharf Rat (SEE CAUTIONS)\n"
            "- (see cautions) Opener\n")
    assert site.parse_briefing(text) == [{"heading": "Set 1", "blocks": [
        {"p": "The tape is missing a chunk of this pairing."},
        {"ul": ["Dark Star runs long", "Wharf Rat", "Opener"]}]}]


def test_parse_briefing_keeps_other_caution_text_byte_identical():
    kept = [
        "Caution (Do Not Stop on Tracks) runs about 9:21.",
        "Mind the cautions here, and see cautions elsewhere.",
        "Mr. Charlie (title disputed; see cautions) opens.",
        "Tuning (see cautions on the title) follows.",
        "A note (see the notes) stays.",
    ]
    text = "## Set 1\n" + "\n".join("- " + k for k in kept) + "\n"
    assert site.parse_briefing(text) == [{"heading": "Set 1", "blocks": [{"ul": kept}]}]


def test_parse_briefing_leaves_a_line_without_the_pointer_unstripped():
    # "**" is removed after the strip, so this line keeps its leading space as before.
    assert site.parse_briefing("## Set 1\n** bold** text\n") == [
        {"heading": "Set 1", "blocks": [{"p": " bold text"}]}]


def test_parse_briefing_strips_a_leading_pointer_from_a_paragraph_line():
    assert site.parse_briefing("## Set 1\n(see cautions) Bar\n") == [
        {"heading": "Set 1", "blocks": [{"p": "Bar"}]}]
